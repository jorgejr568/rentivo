from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.responses import Response

from rentivo.api.app import create_app
from rentivo.api.csrf import CSRF_HEADER_NAME, issue_csrf_token
from rentivo.api.dependencies import get_services
from rentivo.api.principal import Principal
from rentivo.constants.api_scopes import APIScope
from rentivo.models.api_key import APIKey, APIKeyGrant
from rentivo.models.organization import Organization, OrganizationMember
from rentivo.models.user import User
from rentivo.services.api_key_service import IssuedAPIKey
from rentivo.settings import settings

NOW = datetime(2026, 7, 17, 12, tzinfo=UTC)
LOGIN_SECRET = f"rntv-v1-{'L' * 43}"
INTEGRATION_SECRET = f"rntv-v1-{'I' * 43}"
CREATED_SECRET = f"rntv-v1-{'K' * 43}"

USER = User(id=7, email="person@example.com")
ORGANIZATION = Organization(
    id=31,
    uuid="01JORG00000000000000000000",
    name="Administradora Exemplo",
    created_by=USER.id,
)


def _api_key(
    *,
    key_id: int,
    uuid: str,
    name: str,
    is_login_token: bool,
    scopes: frozenset[str],
    grants: tuple[APIKeyGrant, ...] = (),
    key_start: str = "aBcD",
    key_end: str = "yZ",
    user_id: int = USER.id,
) -> APIKey:
    return APIKey(
        id=key_id,
        uuid=uuid,
        user_id=user_id,
        name=name,
        secret_hash=bytes([key_id]) * 32,
        key_start=key_start,
        key_end=key_end,
        is_login_token=is_login_token,
        scopes=scopes,
        grants=grants,
        expires_at=NOW + timedelta(days=90),
        created_at=NOW - timedelta(days=2),
    )


LOGIN_KEY = _api_key(
    key_id=1,
    uuid="01JLOGIN0000000000000000000",
    name="Browser",
    is_login_token=True,
    scopes=frozenset({APIScope.API_KEYS_MANAGE.value}),
)
INTEGRATION_KEY = _api_key(
    key_id=2,
    uuid="01JINTEGRATION0000000000000",
    name="Relatorios",
    is_login_token=False,
    # Deliberately includes the privileged scope to prove key class is enforced too.
    scopes=frozenset({APIScope.API_KEYS_MANAGE.value, APIScope.PROFILE_READ.value}),
    grants=(APIKeyGrant(resource_type="user", resource_id=USER.id),),
)


class FakeAPIKeyService:
    def __init__(self) -> None:
        self.integration_scopes = frozenset({APIScope.PROFILE_READ.value})
        self.live_organization_ids = {ORGANIZATION.id}
        self.keys = [LOGIN_KEY, INTEGRATION_KEY]
        self.credentials = {
            LOGIN_SECRET: LOGIN_KEY,
            INTEGRATION_SECRET: INTEGRATION_KEY,
        }
        self.authenticate_calls: list[str] = []
        self.issue_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.revoke_calls: list[tuple[int, str]] = []

    def authenticate(self, secret: str) -> APIKey | None:
        self.authenticate_calls.append(secret)
        return self.credentials.get(secret)

    def list_integrations(self, user_id: int) -> list[APIKey]:
        return [key for key in self.keys if key.user_id == user_id and not key.is_login_token]

    def get_integration(self, user_id: int, uuid: str) -> APIKey | None:
        return next(
            (key for key in self.keys if key.user_id == user_id and key.uuid == uuid and not key.is_login_token),
            None,
        )

    def _validated_metadata(
        self,
        *,
        user_id: int,
        name: str,
        scopes: Any,
        grants: Any,
    ) -> tuple[str, frozenset[str], tuple[APIKeyGrant, ...]]:
        normalized_name = name.strip()
        normalized_scopes = frozenset(str(scope) for scope in scopes)
        normalized_grants = tuple(grants)
        if not normalized_name:
            raise ValueError("API-key name is required")
        if not normalized_scopes or not normalized_scopes.issubset(self.integration_scopes):
            raise ValueError("API-key scopes must be deployed and integration-safe")
        if not normalized_grants or len(set(normalized_grants)) != len(normalized_grants):
            raise ValueError("API key must have distinct workspace grants")
        for grant in normalized_grants:
            if grant.resource_type == "user" and grant.resource_id != user_id:
                raise ValueError("Personal workspace grant must belong to the key owner")
            if grant.resource_type == "organization" and grant.resource_id not in self.live_organization_ids:
                raise ValueError("Organization workspace grant requires current membership")
        return normalized_name, normalized_scopes, normalized_grants

    def issue_integration(
        self,
        *,
        user_id: int,
        name: str,
        scopes: Any,
        grants: Any,
        expires_at: datetime | None = None,
    ) -> IssuedAPIKey:
        normalized_name, normalized_scopes, normalized_grants = self._validated_metadata(
            user_id=user_id,
            name=name,
            scopes=scopes,
            grants=grants,
        )
        expiration = expires_at or NOW + timedelta(days=90)
        if expiration <= NOW or expiration > NOW + timedelta(days=365):
            raise ValueError("API-key expiration must be within one year")
        self.issue_calls.append(
            {
                "user_id": user_id,
                "name": normalized_name,
                "scopes": normalized_scopes,
                "grants": normalized_grants,
                "expires_at": expiration,
            }
        )
        key = _api_key(
            key_id=3,
            uuid="01JCREATED00000000000000000",
            name=normalized_name,
            is_login_token=False,
            scopes=normalized_scopes,
            grants=normalized_grants,
            key_start="KKKK",
            key_end="KK",
        ).model_copy(update={"expires_at": expiration, "created_at": NOW})
        self.keys.append(key)
        self.credentials[CREATED_SECRET] = key
        return IssuedAPIKey(key=key, secret=CREATED_SECRET)

    def validate_integration(
        self,
        *,
        user_id: int,
        name: str,
        scopes: Any,
        grants: Any,
        expires_at: datetime | None = None,
    ) -> None:
        self._validated_metadata(
            user_id=user_id,
            name=name,
            scopes=scopes,
            grants=grants,
        )
        expiration = expires_at or NOW + timedelta(days=90)
        if expiration <= NOW or expiration > NOW + timedelta(days=365):
            raise ValueError("API-key expiration must be within one year")

    def update_integration(
        self,
        *,
        user_id: int,
        uuid: str,
        name: str,
        scopes: Any,
        grants: Any,
    ) -> APIKey | None:
        existing = self.get_integration(user_id, uuid)
        if existing is None or existing.revoked_at is not None:
            return None
        normalized_name, normalized_scopes, normalized_grants = self._validated_metadata(
            user_id=user_id,
            name=name,
            scopes=scopes,
            grants=grants,
        )
        self.update_calls.append(
            {
                "user_id": user_id,
                "uuid": uuid,
                "name": normalized_name,
                "scopes": normalized_scopes,
                "grants": normalized_grants,
            }
        )
        updated = existing.model_copy(
            update={
                "name": normalized_name,
                "scopes": normalized_scopes,
                "grants": normalized_grants,
            }
        )
        self.keys[self.keys.index(existing)] = updated
        return updated

    def revoke_integration(self, user_id: int, uuid: str) -> bool:
        self.revoke_calls.append((user_id, uuid))
        existing = self.get_integration(user_id, uuid)
        if existing is None:
            return False
        if existing.revoked_at is not None:
            return False
        revoked = existing.model_copy(update={"revoked_at": NOW})
        self.keys[self.keys.index(existing)] = revoked
        return True


class FakeUserService:
    def get_by_id(self, user_id: int) -> User | None:
        return USER if user_id == USER.id else None


class FakeOrganizationService:
    def __init__(self) -> None:
        self.member_user_ids = {USER.id}

    def list_user_organizations(self, user_id: int) -> list[Organization]:
        return [ORGANIZATION] if user_id == USER.id else []

    def get_by_id(self, organization_id: int) -> Organization | None:
        return ORGANIZATION if organization_id == ORGANIZATION.id else None

    def get_by_uuid(self, organization_uuid: str) -> Organization | None:
        return ORGANIZATION if organization_uuid == ORGANIZATION.uuid else None

    def get_member(self, organization_id: int, user_id: int) -> OrganizationMember | None:
        if organization_id != ORGANIZATION.id or user_id not in self.member_user_ids:
            return None
        return OrganizationMember(organization_id=organization_id, user_id=user_id, role="member")


class FakeRateLimitService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.attempts: dict[tuple[str, str], int] = {}

    def reserve(self, *, action: str, identity: str, limit: int, window_seconds: int) -> bool:
        self.calls.append(
            {
                "action": action,
                "identity": identity,
                "limit": limit,
                "window_seconds": window_seconds,
            }
        )
        key = (action, identity)
        self.attempts[key] = self.attempts.get(key, 0) + 1
        return self.attempts[key] <= limit


class FakeAuditService:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def safe_log_for(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


@dataclass(slots=True)
class APIKeyHarness:
    client: TestClient
    app: Any
    api_key: FakeAPIKeyService
    audit: FakeAuditService
    rate_limit: FakeRateLimitService
    organization: FakeOrganizationService


@pytest.fixture()
def api_key_harness(monkeypatch: pytest.MonkeyPatch) -> APIKeyHarness:
    monkeypatch.setattr(settings, "secret_key", "api-key-route-contract-signing-key")
    monkeypatch.setattr(settings, "access_cookie_name", "__Host-rentivo_access")
    monkeypatch.setattr(settings, "csrf_cookie_name", "__Host-rentivo_csrf")
    monkeypatch.setattr(settings, "cookie_secure", True)

    api_key = FakeAPIKeyService()
    audit = FakeAuditService()
    rate_limit = FakeRateLimitService()
    organization = FakeOrganizationService()
    services = SimpleNamespace(
        api_key=api_key,
        mfa=SimpleNamespace(user_requires_mfa_setup=lambda _user_id: False),
        user=FakeUserService(),
        organization=organization,
        audit=audit,
        auth_rate_limit=rate_limit,
    )
    app = create_app()
    app.dependency_overrides[get_services] = lambda: services
    return APIKeyHarness(
        client=TestClient(app),
        app=app,
        api_key=api_key,
        audit=audit,
        rate_limit=rate_limit,
        organization=organization,
    )


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _create_payload(
    *,
    scopes: list[str] | None = None,
    grants: list[dict[str, Any]] | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Automacao financeira",
        "scopes": scopes if scopes is not None else [APIScope.PROFILE_READ.value],
        "grants": grants if grants is not None else [{"resource_type": "user", "resource_id": "personal"}],
    }
    if expires_at is not None:
        payload["expires_at"] = _iso(expires_at)
    return payload


def _login_headers(*, csrf: bool) -> dict[str, str]:
    cookie = f"{settings.access_cookie_name}={LOGIN_SECRET}"
    headers: dict[str, str] = {"Cookie": cookie}
    if csrf:
        token = issue_csrf_token(Response(), Principal(user=USER, api_key=LOGIN_KEY, source="web"))
        headers["Cookie"] = f"{cookie}; {settings.csrf_cookie_name}={token}"
        headers[CSRF_HEADER_NAME] = token
    return headers


def _integration_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {INTEGRATION_SECRET}"}


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _assert_visible_key(payload: dict[str, Any], key: APIKey) -> None:
    assert payload["uuid"] == key.uuid
    assert payload["name"] == key.name
    assert payload["hint"] == f"rntv-v1-{key.key_start}••••{key.key_end}"
    assert set(payload["scopes"]) == set(key.scopes)
    expected_grants = []
    for grant in key.grants:
        if grant.resource_type == "user":
            expected_grants.append({"resource_type": "user", "resource_id": "personal", "available": True})
        elif grant.resource_id == ORGANIZATION.id:
            expected_grants.append(
                {"resource_type": "organization", "resource_id": ORGANIZATION.uuid, "available": True}
            )
        else:
            expected_grants.append({"resource_type": "organization", "resource_id": None, "available": False})
    assert payload["grants"] == expected_grants
    assert _parse_timestamp(payload["expires_at"]) == key.expires_at
    assert payload["last_used_at"] is None
    assert _parse_timestamp(payload["created_at"]) == key.created_at
    assert payload["revoked_at"] is None
    assert {
        "id",
        "user_id",
        "secret",
        "secret_hash",
        "key_start",
        "key_end",
        "is_login_token",
    }.isdisjoint(payload)


def _assert_safe_audit_call(
    call: tuple[tuple[Any, ...], dict[str, Any]],
    *,
    event_type: str,
    key: APIKey,
) -> None:
    args, kwargs = call
    assert args[0].user_id == USER.id
    assert args[0].api_key_uuid == LOGIN_KEY.uuid
    assert args[1] == event_type
    assert kwargs["entity_type"] == "api_key"
    assert kwargs["entity_id"] == key.id
    assert kwargs["entity_uuid"] == key.uuid

    serialized = repr(kwargs)
    assert key.name in serialized
    assert CREATED_SECRET not in serialized
    assert key.secret_hash.hex() not in serialized
    assert key.key_start not in serialized
    assert key.key_end not in serialized
    assert "secret_hash" not in serialized
    assert "is_login_token" not in serialized
    assert "hint" not in serialized


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/api/v1/api-keys", None),
        ("POST", "/api/v1/api-keys", _create_payload()),
        ("GET", f"/api/v1/api-keys/{INTEGRATION_KEY.uuid}", None),
        ("PATCH", f"/api/v1/api-keys/{INTEGRATION_KEY.uuid}", _create_payload()),
        ("DELETE", f"/api/v1/api-keys/{INTEGRATION_KEY.uuid}", None),
        ("GET", "/api/v1/api-keys/options", None),
    ],
)
def test_integration_key_cannot_access_any_management_operation_even_with_privileged_scope(
    api_key_harness: APIKeyHarness,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    response = api_key_harness.client.request(
        method,
        path,
        json=payload,
        headers=_integration_headers(),
    )

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "login_token_required"
    assert api_key_harness.api_key.issue_calls == []
    assert api_key_harness.api_key.update_calls == []
    assert api_key_harness.api_key.revoke_calls == []


def test_options_exposes_only_safe_deployed_scopes_and_current_workspaces(
    api_key_harness: APIKeyHarness,
) -> None:
    response = api_key_harness.client.get(
        "/api/v1/api-keys/options",
        headers=_login_headers(csrf=False),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scopes"] == [APIScope.PROFILE_READ.value]
    assert payload["default_expiration_days"] == 90
    assert payload["max_expiration_days"] == 365
    assert payload["personal_workspace"]["resource_type"] == "user"
    assert payload["personal_workspace"]["resource_id"] == "personal"
    assert payload["organizations"] == [
        {
            "resource_type": "organization",
            "resource_id": ORGANIZATION.uuid,
            "name": ORGANIZATION.name,
        }
    ]
    assert APIScope.API_KEYS_MANAGE.value not in response.text
    assert APIScope.BILLINGS_READ.value not in response.text


def test_list_omits_hidden_login_tokens_and_returns_only_masked_metadata(
    api_key_harness: APIKeyHarness,
) -> None:
    response = api_key_harness.client.get(
        "/api/v1/api-keys",
        headers=_login_headers(csrf=False),
    )

    assert response.status_code == 200
    assert [item["uuid"] for item in response.json()["items"]] == [INTEGRATION_KEY.uuid]
    _assert_visible_key(response.json()["items"][0], INTEGRATION_KEY)
    assert LOGIN_KEY.uuid not in response.text
    assert LOGIN_SECRET not in response.text
    assert INTEGRATION_SECRET not in response.text


def test_unresolvable_stale_grant_is_preserved_without_leaking_its_internal_id(
    api_key_harness: APIKeyHarness,
) -> None:
    stale = _api_key(
        key_id=4,
        uuid="01JSTALEINTEGRATION00000000",
        name="Workspace removido",
        is_login_token=False,
        scopes=frozenset({APIScope.PROFILE_READ.value}),
        grants=(APIKeyGrant(resource_type="organization", resource_id=999),),
    )
    api_key_harness.api_key.keys.append(stale)

    response = api_key_harness.client.get(
        f"/api/v1/api-keys/{stale.uuid}",
        headers=_login_headers(csrf=False),
    )

    assert response.status_code == 200
    assert response.json()["grants"] == [{"resource_type": "organization", "resource_id": None, "available": False}]
    assert "999" not in response.text


def test_existing_organization_grant_is_unavailable_after_membership_removal(
    api_key_harness: APIKeyHarness,
) -> None:
    organization_key = _api_key(
        key_id=4,
        uuid="01JREMOVEDMEMBERSHIP000000",
        name="Membership removida",
        is_login_token=False,
        scopes=frozenset({APIScope.PROFILE_READ.value}),
        grants=(APIKeyGrant(resource_type="organization", resource_id=ORGANIZATION.id),),
    )
    api_key_harness.api_key.keys.append(organization_key)
    api_key_harness.organization.member_user_ids.clear()

    response = api_key_harness.client.get(
        f"/api/v1/api-keys/{organization_key.uuid}",
        headers=_login_headers(csrf=False),
    )

    assert response.status_code == 200
    assert response.json()["grants"] == [
        {"resource_type": "organization", "resource_id": ORGANIZATION.uuid, "available": False}
    ]


def test_hidden_login_token_cannot_be_retrieved_through_management_detail(
    api_key_harness: APIKeyHarness,
) -> None:
    response = api_key_harness.client.get(
        f"/api/v1/api-keys/{LOGIN_KEY.uuid}",
        headers=_login_headers(csrf=False),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert LOGIN_KEY.uuid not in response.text
    assert api_key_harness.api_key.authenticate_calls == [LOGIN_SECRET]


def test_create_discloses_full_secret_once_with_no_store_and_safe_audit(
    api_key_harness: APIKeyHarness,
) -> None:
    response = api_key_harness.client.post(
        "/api/v1/api-keys",
        json=_create_payload(),
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    created_payload = response.json()
    assert created_payload["secret"] == CREATED_SECRET
    created_key = api_key_harness.api_key.get_integration(USER.id, created_payload["uuid"])
    assert created_key is not None
    _assert_visible_key({key: value for key, value in created_payload.items() if key != "secret"}, created_key)

    detail = api_key_harness.client.get(
        f"/api/v1/api-keys/{created_key.uuid}",
        headers=_login_headers(csrf=False),
    )
    assert detail.status_code == 200
    _assert_visible_key(detail.json(), created_key)
    assert CREATED_SECRET not in detail.text

    assert len(api_key_harness.audit.calls) == 1
    _assert_safe_audit_call(api_key_harness.audit.calls[0], event_type="api_key.create", key=created_key)


def test_create_rate_limit_is_user_scoped_shared_and_blocks_before_issuance_or_audit(
    api_key_harness: APIKeyHarness,
) -> None:
    responses = [
        api_key_harness.client.post(
            "/api/v1/api-keys",
            json=_create_payload(),
            headers=_login_headers(csrf=True),
        )
        for _ in range(11)
    ]

    assert [response.status_code for response in responses] == ([201] * 10) + [429]
    assert responses[-1].json()["code"] == "api_key_creation_rate_limited"
    assert responses[-1].json()["detail"] == ("Muitas chaves de integração foram criadas. Tente novamente mais tarde.")
    assert len(api_key_harness.api_key.issue_calls) == 10
    assert len(api_key_harness.audit.calls) == 10
    assert len(api_key_harness.rate_limit.calls) == 11
    assert api_key_harness.rate_limit.calls[-1] == {
        "action": "api_key_create",
        "identity": f"user:{USER.id}",
        "limit": 10,
        "window_seconds": 3600,
    }


def test_service_validation_errors_do_not_echo_secret_material(
    api_key_harness: APIKeyHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_creation(**_kwargs: Any) -> None:
        raise ValueError(CREATED_SECRET)

    monkeypatch.setattr(api_key_harness.api_key, "issue_integration", reject_creation)

    response = api_key_harness.client.post(
        "/api/v1/api-keys",
        json=_create_payload(),
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert CREATED_SECRET not in response.text
    assert api_key_harness.audit.calls == []


def test_create_defaults_to_90_days(
    api_key_harness: APIKeyHarness,
) -> None:
    response = api_key_harness.client.post(
        "/api/v1/api-keys",
        json=_create_payload(),
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == 201
    assert _parse_timestamp(response.json()["expires_at"]) == NOW + timedelta(days=90)
    assert api_key_harness.api_key.issue_calls[0]["expires_at"] == NOW + timedelta(days=90)


@pytest.mark.parametrize(
    ("expires_at", "expected_status"),
    [
        (NOW + timedelta(days=365), 201),
        (NOW + timedelta(days=365, seconds=1), 422),
        (NOW, 422),
    ],
)
def test_create_enforces_positive_expiration_with_a_one_year_maximum(
    api_key_harness: APIKeyHarness,
    expires_at: datetime,
    expected_status: int,
) -> None:
    response = api_key_harness.client.post(
        "/api/v1/api-keys",
        json=_create_payload(expires_at=expires_at),
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == expected_status
    if expected_status == 201:
        assert _parse_timestamp(response.json()["expires_at"]) == expires_at
    else:
        assert response.json()["code"] == "validation_error"
        assert api_key_harness.api_key.issue_calls == []


@pytest.mark.parametrize(
    "scopes",
    [
        [],
        [APIScope.API_KEYS_MANAGE.value],
        [APIScope.BILLINGS_READ.value],
        ["unknown:scope"],
    ],
)
def test_create_rejects_empty_privileged_undeployed_and_unknown_scopes(
    api_key_harness: APIKeyHarness,
    scopes: list[str],
) -> None:
    response = api_key_harness.client.post(
        "/api/v1/api-keys",
        json=_create_payload(scopes=scopes),
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert api_key_harness.api_key.issue_calls == []


def test_create_accepts_owner_personal_and_current_organization_grants(
    api_key_harness: APIKeyHarness,
) -> None:
    grants = [
        {"resource_type": "user", "resource_id": "personal"},
        {"resource_type": "organization", "resource_id": ORGANIZATION.uuid},
    ]
    response = api_key_harness.client.post(
        "/api/v1/api-keys",
        json=_create_payload(grants=grants),
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == 201
    assert response.json()["grants"] == [
        {"resource_type": "user", "resource_id": "personal", "available": True},
        {"resource_type": "organization", "resource_id": ORGANIZATION.uuid, "available": True},
    ]
    assert api_key_harness.api_key.issue_calls[0]["grants"] == (
        APIKeyGrant(resource_type="user", resource_id=USER.id),
        APIKeyGrant(resource_type="organization", resource_id=ORGANIZATION.id),
    )


@pytest.mark.parametrize(
    "grants",
    [
        [],
        [{"resource_type": "user", "resource_id": "not-personal"}],
        [{"resource_type": "organization", "resource_id": "personal"}],
        [{"resource_type": "organization", "resource_id": "missing-organization"}],
        [
            {"resource_type": "user", "resource_id": "personal"},
            {"resource_type": "user", "resource_id": "personal"},
        ],
    ],
)
def test_create_rejects_missing_foreign_nonmember_and_duplicate_grants(
    api_key_harness: APIKeyHarness,
    grants: list[dict[str, Any]],
) -> None:
    response = api_key_harness.client.post(
        "/api/v1/api-keys",
        json=_create_payload(grants=grants),
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert api_key_harness.api_key.issue_calls == []
    assert api_key_harness.rate_limit.calls == []


def test_organization_grant_is_rejected_after_membership_is_removed(
    api_key_harness: APIKeyHarness,
) -> None:
    api_key_harness.api_key.live_organization_ids.clear()

    response = api_key_harness.client.post(
        "/api/v1/api-keys",
        json=_create_payload(
            grants=[{"resource_type": "organization", "resource_id": ORGANIZATION.uuid}],
        ),
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert api_key_harness.api_key.issue_calls == []


def test_patch_updates_only_name_safe_scopes_and_grants_with_safe_audit(
    api_key_harness: APIKeyHarness,
) -> None:
    original_expiration = INTEGRATION_KEY.expires_at
    payload = {
        "name": "Relatorios pessoais e organizacionais",
        "scopes": [APIScope.PROFILE_READ.value],
        "grants": [
            {"resource_type": "user", "resource_id": "personal"},
            {"resource_type": "organization", "resource_id": ORGANIZATION.uuid},
        ],
    }

    response = api_key_harness.client.patch(
        f"/api/v1/api-keys/{INTEGRATION_KEY.uuid}",
        json=payload,
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == 200
    updated = api_key_harness.api_key.get_integration(USER.id, INTEGRATION_KEY.uuid)
    assert updated is not None
    _assert_visible_key(response.json(), updated)
    assert updated.expires_at == original_expiration
    assert INTEGRATION_SECRET not in response.text
    assert len(api_key_harness.audit.calls) == 1
    _assert_safe_audit_call(api_key_harness.audit.calls[0], event_type="api_key.update", key=updated)


@pytest.mark.parametrize("payload", [{}, {"name": None}])
def test_patch_requires_at_least_one_non_null_mutable_field(
    api_key_harness: APIKeyHarness,
    payload: dict[str, Any],
) -> None:
    response = api_key_harness.client.patch(
        f"/api/v1/api-keys/{INTEGRATION_KEY.uuid}",
        json=payload,
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert api_key_harness.api_key.update_calls == []


def test_patch_applies_safe_scope_and_current_membership_validation(
    api_key_harness: APIKeyHarness,
) -> None:
    response = api_key_harness.client.patch(
        f"/api/v1/api-keys/{INTEGRATION_KEY.uuid}",
        json={"scopes": [APIScope.API_KEYS_MANAGE.value]},
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert api_key_harness.api_key.update_calls == []
    assert api_key_harness.audit.calls == []


def test_patch_rejects_an_unknown_public_organization_identifier(
    api_key_harness: APIKeyHarness,
) -> None:
    response = api_key_harness.client.patch(
        f"/api/v1/api-keys/{INTEGRATION_KEY.uuid}",
        json={"grants": [{"resource_type": "organization", "resource_id": "missing-organization"}]},
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert api_key_harness.api_key.update_calls == []
    assert api_key_harness.audit.calls == []


def test_patch_rejects_a_revoked_integration_key(
    api_key_harness: APIKeyHarness,
) -> None:
    existing = api_key_harness.api_key.get_integration(USER.id, INTEGRATION_KEY.uuid)
    assert existing is not None
    revoked = existing.model_copy(update={"revoked_at": NOW})
    api_key_harness.api_key.keys[api_key_harness.api_key.keys.index(existing)] = revoked

    response = api_key_harness.client.patch(
        f"/api/v1/api-keys/{INTEGRATION_KEY.uuid}",
        json={"name": "Novo nome"},
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert api_key_harness.audit.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expires_at", _iso(NOW + timedelta(days=30))),
        ("secret", CREATED_SECRET),
        ("is_login_token", True),
        ("revoked_at", _iso(NOW)),
    ],
)
def test_patch_rejects_immutable_or_internal_fields(
    api_key_harness: APIKeyHarness,
    field: str,
    value: Any,
) -> None:
    payload = _create_payload()
    payload[field] = value

    response = api_key_harness.client.patch(
        f"/api/v1/api-keys/{INTEGRATION_KEY.uuid}",
        json=payload,
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert api_key_harness.api_key.update_calls == []
    assert api_key_harness.audit.calls == []


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/api/v1/api-keys", _create_payload()),
        ("PATCH", f"/api/v1/api-keys/{INTEGRATION_KEY.uuid}", _create_payload()),
        ("DELETE", f"/api/v1/api-keys/{INTEGRATION_KEY.uuid}", None),
    ],
)
def test_cookie_authenticated_mutations_require_csrf_before_service_or_audit(
    api_key_harness: APIKeyHarness,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    response = api_key_harness.client.request(
        method,
        path,
        json=payload,
        headers=_login_headers(csrf=False),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    assert api_key_harness.api_key.issue_calls == []
    assert api_key_harness.api_key.update_calls == []
    assert api_key_harness.api_key.revoke_calls == []
    assert api_key_harness.audit.calls == []


def test_revoke_is_idempotent_soft_deletion_and_audits_only_the_transition(
    api_key_harness: APIKeyHarness,
) -> None:
    path = f"/api/v1/api-keys/{INTEGRATION_KEY.uuid}"

    first = api_key_harness.client.delete(path, headers=_login_headers(csrf=True))
    second = api_key_harness.client.delete(path, headers=_login_headers(csrf=True))

    assert [first.status_code, second.status_code] == [204, 204]
    assert first.content == second.content == b""
    assert api_key_harness.api_key.revoke_calls == [
        (USER.id, INTEGRATION_KEY.uuid),
        (USER.id, INTEGRATION_KEY.uuid),
    ]
    revoked = api_key_harness.api_key.get_integration(USER.id, INTEGRATION_KEY.uuid)
    assert revoked is not None
    assert revoked.revoked_at == NOW
    assert len(api_key_harness.audit.calls) == 1
    _assert_safe_audit_call(api_key_harness.audit.calls[0], event_type="api_key.revoke", key=revoked)


def test_revoke_returns_not_found_when_the_key_disappears_during_the_operation(
    api_key_harness: APIKeyHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def disappear(user_id: int, uuid: str) -> bool:
        api_key_harness.api_key.keys = [key for key in api_key_harness.api_key.keys if key.uuid != uuid]
        return False

    monkeypatch.setattr(api_key_harness.api_key, "revoke_integration", disappear)

    response = api_key_harness.client.delete(
        f"/api/v1/api-keys/{INTEGRATION_KEY.uuid}",
        headers=_login_headers(csrf=True),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert api_key_harness.audit.calls == []


def test_api_key_openapi_exposes_strict_crud_and_one_time_secret_contracts(
    api_key_harness: APIKeyHarness,
) -> None:
    schema = api_key_harness.app.openapi()
    expected_operations = {
        "/api/v1/api-keys": {"get", "post"},
        "/api/v1/api-keys/{key_uuid}": {"get", "patch", "delete"},
        "/api/v1/api-keys/options": {"get"},
    }

    for path, methods in expected_operations.items():
        assert path in schema["paths"]
        for method in methods:
            operation = schema["paths"][path][method]
            assert operation["operationId"]
            assert "api-keys" in operation["tags"]

    collection = schema["paths"]["/api/v1/api-keys"]
    assert "application/json" in collection["post"]["requestBody"]["content"]
    assert {"201", "422", "429"}.issubset(collection["post"]["responses"])
    detail = schema["paths"]["/api/v1/api-keys/{key_uuid}"]
    assert {"200", "404", "422"}.issubset(detail["patch"]["responses"])
    assert "204" in detail["delete"]["responses"]

    components = schema["components"]["schemas"]
    create_request = components["APIKeyCreateRequest"]
    update_request = components["APIKeyUpdateRequest"]
    visible_response = components["APIKeyResponse"]
    create_response = components["APIKeyCreateResponse"]
    grant_request = components["APIKeyGrantRequest"]
    grant_response = components["APIKeyGrantResponse"]
    personal_option = components["PersonalWorkspaceOption"]
    organization_option = components["OrganizationWorkspaceOption"]

    assert create_request["additionalProperties"] is False
    assert set(create_request["required"]) == {"name", "scopes", "grants"}
    assert set(update_request["properties"]) == {"name", "scopes", "grants"}
    assert update_request["additionalProperties"] is False
    assert {
        "secret",
        "secret_hash",
        "key_start",
        "key_end",
        "is_login_token",
    }.isdisjoint(visible_response["properties"])
    assert "secret" in create_response["properties"]
    assert create_response["properties"]["secret"]["type"] == "string"
    assert grant_request["properties"]["resource_id"]["type"] == "string"
    assert "integer" not in repr(grant_response["properties"]["resource_id"])
    assert personal_option["properties"]["resource_id"]["const"] == "personal"
    assert organization_option["properties"]["resource_id"]["type"] == "string"
