from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from rentivo.api.app import create_app
from rentivo.api.dependencies import get_services
from rentivo.constants.api_scopes import APIScope
from rentivo.models.api_key import APIKey, APIKeyGrant
from rentivo.models.user import User

NOW = datetime(2026, 7, 17, 12, tzinfo=UTC)
USER = User(id=7, email="profile-user@example.com", password_hash="must-not-leak", pix_key="pix-must-not-leak")
PERSONAL_SECRET = f"rntv-v1-{'P' * 43}"
ORG_ONLY_SECRET = f"rntv-v1-{'O' * 43}"


def _key(*, secret_hash: bytes, grants: tuple[APIKeyGrant, ...], scopes: frozenset[str]) -> APIKey:
    return APIKey(
        id=1,
        uuid=f"profile-key-{secret_hash[0]}",
        user_id=USER.id,
        name="Profile integration",
        secret_hash=secret_hash,
        key_start="abcd",
        key_end="yz",
        scopes=scopes,
        grants=grants,
        expires_at=NOW + timedelta(days=30),
    )


PERSONAL_KEY = _key(
    secret_hash=b"p" * 32,
    scopes=frozenset({APIScope.PROFILE_READ.value}),
    grants=(APIKeyGrant(resource_type="user", resource_id=USER.id),),
)
ORG_ONLY_KEY = _key(
    secret_hash=b"o" * 32,
    scopes=frozenset({APIScope.PROFILE_READ.value}),
    grants=(APIKeyGrant(resource_type="organization", resource_id=42),),
)


class FakeAPIKeyService:
    def authenticate(self, secret: str) -> APIKey | None:
        return {PERSONAL_SECRET: PERSONAL_KEY, ORG_ONLY_SECRET: ORG_ONLY_KEY}.get(secret)

    @staticmethod
    def can_access_resource(key: APIKey, resource_type: str, resource_id: int) -> bool:
        return APIKeyGrant(resource_type=resource_type, resource_id=resource_id) in key.grants


class FakeUserService:
    @staticmethod
    def get_by_id(user_id: int) -> User | None:
        return USER if user_id == USER.id else None


def _client() -> tuple[TestClient, object]:
    services = SimpleNamespace(api_key=FakeAPIKeyService(), user=FakeUserService())
    app = create_app()
    app.dependency_overrides[get_services] = lambda: services
    return TestClient(app), app


def test_personal_integration_key_reads_only_non_security_profile() -> None:
    client, _app = _client()

    response = client.get(
        "/api/v1/profile",
        headers={"Authorization": f"Bearer {PERSONAL_SECRET}"},
    )

    assert response.status_code == 200
    assert response.json() == {"email": USER.email}
    assert str(USER.id) not in response.text
    assert USER.password_hash not in response.text
    assert USER.pix_key not in response.text
    assert "is_login_token" not in response.text


def test_organization_only_key_cannot_read_personal_profile() -> None:
    client, _app = _client()

    response = client.get(
        "/api/v1/profile",
        headers={"Authorization": f"Bearer {ORG_ONLY_SECRET}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_profile_requires_profile_read_scope() -> None:
    client, _app = _client()
    key_without_scope = PERSONAL_KEY.model_copy(update={"scopes": frozenset()})
    client.app.dependency_overrides[get_services] = lambda: SimpleNamespace(
        api_key=SimpleNamespace(
            authenticate=lambda _secret: key_without_scope,
            can_access_resource=FakeAPIKeyService.can_access_resource,
        ),
        user=FakeUserService(),
    )

    response = client.get(
        "/api/v1/profile",
        headers={"Authorization": f"Bearer {PERSONAL_SECRET}"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "missing_scope"


def test_profile_operation_is_typed_in_openapi() -> None:
    _client_value, app = _client()

    operation = app.openapi()["paths"]["/api/v1/profile"]["get"]

    assert "profile" in operation["tags"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/CurrentProfileResponse")
    profile_schema = app.openapi()["components"]["schemas"]["CurrentProfileResponse"]
    assert set(profile_schema["properties"]) == {"email"}
