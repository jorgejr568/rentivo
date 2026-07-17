from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from rentivo.api.authentication import get_principal
from rentivo.api.principal import Principal

from rentivo.api.app import create_app
from rentivo.api.dependencies import require_login_scope, require_resource_grant, require_scope
from rentivo.api.errors import ProblemException
from rentivo.constants.api_scopes import APIScope
from rentivo.context import Actor
from rentivo.models.api_key import APIKey, APIKeyGrant
from rentivo.models.user import User


def _principal(
    *,
    is_login_token: bool,
    scopes: frozenset[str],
    source: str | None = None,
) -> Principal:
    key = APIKey(
        id=1,
        uuid="login-key" if is_login_token else "integration-key",
        user_id=7,
        name="Browser" if is_login_token else "Export",
        secret_hash=b"x" * 32,
        key_start="abcd",
        key_end="yz",
        is_login_token=is_login_token,
        scopes=scopes,
        grants=(APIKeyGrant(resource_type="organization", resource_id=42),),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return Principal(
        user=User(id=7, email="person@example.com"),
        api_key=key,
        source=source or ("web" if is_login_token else "integration"),
    )


def _authorization_client(principal: Principal) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_principal] = lambda: principal

    @app.get("/api/v1/test/profile")
    async def profile(
        authenticated: Principal = Depends(require_scope(APIScope.PROFILE_READ)),
    ) -> dict[str, int | None]:
        return {"user_id": authenticated.user.id}

    @app.post("/api/v1/test/api-keys")
    async def manage_api_keys(
        authenticated: Principal = Depends(require_login_scope(APIScope.API_KEYS_MANAGE)),
    ) -> dict[str, int | None]:
        return {"user_id": authenticated.user.id}

    return TestClient(app)


def test_required_scope_returns_the_principal() -> None:
    principal = _principal(is_login_token=False, scopes=frozenset({APIScope.PROFILE_READ.value}))

    with _authorization_client(principal) as client:
        response = client.get("/api/v1/test/profile")

    assert response.status_code == 200
    assert response.json() == {"user_id": 7}


def test_missing_scope_returns_stable_forbidden_problem() -> None:
    principal = _principal(is_login_token=False, scopes=frozenset())

    with _authorization_client(principal) as client:
        response = client.get("/api/v1/test/profile")

    assert response.status_code == 403
    assert response.json()["code"] == "missing_scope"


def test_login_scope_requires_both_scope_and_interactive_login_token() -> None:
    integration = _principal(
        is_login_token=False,
        scopes=frozenset({APIScope.API_KEYS_MANAGE.value}),
    )

    with _authorization_client(integration) as client:
        response = client.post("/api/v1/test/api-keys")

    assert response.status_code == 403
    assert response.json()["code"] == "login_token_required"


def test_login_scope_checks_scope_before_key_class() -> None:
    integration = _principal(is_login_token=False, scopes=frozenset())

    with _authorization_client(integration) as client:
        response = client.post("/api/v1/test/api-keys")

    assert response.status_code == 403
    assert response.json()["code"] == "missing_scope"


def test_login_token_with_required_scope_is_allowed() -> None:
    login = _principal(
        is_login_token=True,
        scopes=frozenset({APIScope.API_KEYS_MANAGE.value}),
    )

    with _authorization_client(login) as client:
        response = client.post("/api/v1/test/api-keys")

    assert response.status_code == 200
    assert response.json() == {"user_id": 7}


def test_resource_outside_effective_grants_is_a_non_disclosing_not_found() -> None:
    principal = _principal(is_login_token=False, scopes=frozenset({APIScope.ORGANIZATIONS_READ.value}))
    api_key_service = MagicMock()
    api_key_service.can_access_resource.return_value = False
    services = SimpleNamespace(api_key=api_key_service)

    with pytest.raises(ProblemException) as captured:
        require_resource_grant(principal, services, "organization", 42)

    problem = captured.value.problem
    assert problem.status == 404
    assert problem.code == "not_found"
    assert problem.detail == "Recurso não encontrado."
    assert "42" not in problem.model_dump_json()
    api_key_service.can_access_resource.assert_called_once_with(principal.api_key, "organization", 42)


def test_resource_dependency_delegates_dynamic_and_persisted_access_to_api_key_service() -> None:
    login = _principal(is_login_token=True, scopes=frozenset({APIScope.ORGANIZATIONS_READ.value}))
    integration = _principal(is_login_token=False, scopes=frozenset({APIScope.ORGANIZATIONS_READ.value}))
    api_key_service = MagicMock()
    api_key_service.can_access_resource.return_value = True
    services = SimpleNamespace(api_key=api_key_service)

    assert require_resource_grant(login, services, "organization", 42) is None
    assert require_resource_grant(integration, services, "organization", 42) is None
    assert api_key_service.can_access_resource.call_args_list == [
        ((login.api_key, "organization", 42),),
        ((integration.api_key, "organization", 42),),
    ]


@pytest.mark.parametrize(
    ("source", "is_login_token"),
    [
        ("web", True),
        ("mobile", True),
        ("integration", False),
    ],
)
def test_principal_actor_attributes_api_key_class_and_transport(
    source: str,
    is_login_token: bool,
) -> None:
    principal = _principal(
        is_login_token=is_login_token,
        scopes=frozenset({APIScope.PROFILE_READ.value}),
        source=source,
    )

    assert principal.actor == Actor(
        user_id=7,
        email="person@example.com",
        source=source,
        api_key_uuid=principal.api_key.uuid,
        is_login_token=is_login_token,
    )
