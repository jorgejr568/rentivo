from __future__ import annotations

import importlib
import importlib.util
import inspect
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import Response
from fastapi.testclient import TestClient

from rentivo.api.app import create_app
from rentivo.api.csrf import CSRF_HEADER_NAME, issue_csrf_token
from rentivo.api.dependencies import get_services
from rentivo.api.principal import Principal
from rentivo.constants.api_scopes import APIScope
from rentivo.models.api_key import APIKey, APIKeyGrant
from rentivo.models.audit_log import AuditEventType
from rentivo.models.billing import Billing
from rentivo.models.organization import Organization, OrganizationMember
from rentivo.models.theme import AVAILABLE_FONTS, DEFAULT_THEME, Theme
from rentivo.models.user import User
from rentivo.services.audit_serializers import serialize_theme
from rentivo.services.theme_service import ResolvedTheme
from rentivo.settings import settings

NOW = datetime(2026, 7, 18, 12, tzinfo=UTC)
USER = User(id=7, email="theme-user@example.com", password_hash="must-not-leak")
ORGANIZATION = Organization(id=42, uuid="org-42", name="Theme Org", created_by=USER.id)
PERSONAL_BILLING = Billing(
    id=100,
    uuid="personal-billing",
    name="Personal Billing",
    owner_type="user",
    owner_id=USER.id,
)
ORGANIZATION_BILLING = Billing(
    id=200,
    uuid="organization-billing",
    name="Organization Billing",
    owner_type="organization",
    owner_id=ORGANIZATION.id,
)

LOGIN_SECRET = f"rntv-v1-{'L' * 43}"
PERSONAL_SECRET = f"rntv-v1-{'P' * 43}"
ORGANIZATION_SECRET = f"rntv-v1-{'O' * 43}"
NO_SCOPE_SECRET = f"rntv-v1-{'S' * 43}"
READ_ONLY_SECRET = f"rntv-v1-{'R' * 43}"
NO_GRANT_SECRET = f"rntv-v1-{'G' * 43}"

THEME_SCOPES = frozenset({APIScope.THEMES_READ.value, APIScope.THEMES_WRITE.value})
THEME_PAYLOAD = {
    "header_font": "Roboto",
    "text_font": "Open Sans",
    "primary": "#112233",
    "primary_light": "#DDEEFF",
    "secondary": "#445566",
    "secondary_dark": "#223344",
    "text_color": "#101010",
    "text_contrast": "#FAFAFA",
}
DEFAULT_VALUES = {
    "header_font": DEFAULT_THEME.header_font,
    "text_font": DEFAULT_THEME.text_font,
    "primary": DEFAULT_THEME.primary,
    "primary_light": DEFAULT_THEME.primary_light,
    "secondary": DEFAULT_THEME.secondary,
    "secondary_dark": DEFAULT_THEME.secondary_dark,
    "text_color": DEFAULT_THEME.text_color,
    "text_contrast": DEFAULT_THEME.text_contrast,
}


def _key(
    marker: str,
    *,
    scopes: frozenset[str] = THEME_SCOPES,
    grants: tuple[APIKeyGrant, ...],
    is_login_token: bool = False,
) -> APIKey:
    return APIKey(
        id=ord(marker),
        uuid=f"theme-key-{marker}",
        user_id=USER.id,
        name=f"Theme key {marker}",
        secret_hash=marker.encode() * 32,
        key_start=marker * 4,
        key_end=marker * 2,
        is_login_token=is_login_token,
        scopes=scopes,
        grants=grants,
        expires_at=NOW + timedelta(days=30),
    )


PERSONAL_GRANT = APIKeyGrant(resource_type="user", resource_id=USER.id)
ORGANIZATION_GRANT = APIKeyGrant(resource_type="organization", resource_id=ORGANIZATION.id)
LOGIN_KEY = _key(
    "L",
    grants=(PERSONAL_GRANT, ORGANIZATION_GRANT),
    is_login_token=True,
)
PERSONAL_KEY = _key("P", grants=(PERSONAL_GRANT,))
ORGANIZATION_KEY = _key("O", grants=(ORGANIZATION_GRANT,))
NO_SCOPE_KEY = _key("S", scopes=frozenset(), grants=(PERSONAL_GRANT, ORGANIZATION_GRANT))
READ_ONLY_KEY = _key(
    "R",
    scopes=frozenset({APIScope.THEMES_READ.value}),
    grants=(PERSONAL_GRANT, ORGANIZATION_GRANT),
)
NO_GRANT_KEY = _key("G", grants=())


class FakeAPIKeyService:
    keys = {
        LOGIN_SECRET: LOGIN_KEY,
        PERSONAL_SECRET: PERSONAL_KEY,
        ORGANIZATION_SECRET: ORGANIZATION_KEY,
        NO_SCOPE_SECRET: NO_SCOPE_KEY,
        READ_ONLY_SECRET: READ_ONLY_KEY,
        NO_GRANT_SECRET: NO_GRANT_KEY,
    }

    def authenticate(self, secret: str) -> APIKey | None:
        return self.keys.get(secret)

    @staticmethod
    def can_access_resource(key: APIKey, resource_type: str, resource_id: int) -> bool:
        return APIKeyGrant(resource_type=resource_type, resource_id=resource_id) in key.grants


class FakeThemeService:
    def __init__(self) -> None:
        self.themes: dict[tuple[str, int], Theme] = {}
        self.next_id = 1
        self.previewed_themes: list[Theme] = []

    def get_theme_for_owner(self, owner_type: str, owner_id: int) -> Theme | None:
        return self.themes.get((owner_type, owner_id))

    def resolve_theme_with_source(self, billing: Billing) -> ResolvedTheme:
        billing_theme = self.themes.get(("billing", billing.id))
        if billing_theme is not None:
            return ResolvedTheme(theme=billing_theme, source="billing")
        owner_theme = self.themes.get((billing.owner_type, billing.owner_id))
        if owner_theme is not None:
            return ResolvedTheme(theme=owner_theme, source=billing.owner_type)
        return ResolvedTheme(theme=DEFAULT_THEME, source="default")

    def create_or_update_theme(self, owner_type: str, owner_id: int, **fields: str) -> Theme:
        existing = self.themes.get((owner_type, owner_id))
        if existing is not None:
            for name, value in fields.items():
                setattr(existing, name, value)
            return existing
        theme = Theme(
            id=self.next_id,
            uuid=f"theme-{self.next_id}",
            owner_type=owner_type,
            owner_id=owner_id,
            **fields,
        )
        self.next_id += 1
        self.themes[(owner_type, owner_id)] = theme
        return theme

    def delete_theme(self, owner_type: str, owner_id: int) -> bool:
        return self.themes.pop((owner_type, owner_id), None) is not None

    def render_preview(self, theme: Theme) -> bytes:
        self.previewed_themes.append(theme)
        return b"%PDF-service-preview"


class FakeOrganizationService:
    def __init__(self, roles: dict[tuple[int, int], str]) -> None:
        self.roles = roles

    @staticmethod
    def get_by_uuid(uuid: str) -> Organization | None:
        return ORGANIZATION if uuid == ORGANIZATION.uuid else None

    def get_member(self, organization_id: int, user_id: int) -> OrganizationMember | None:
        role = self.roles.get((organization_id, user_id))
        if role is None:
            return None
        return OrganizationMember(organization_id=organization_id, user_id=user_id, email=USER.email, role=role)


class FakeBillingService:
    @staticmethod
    def get_billing_by_uuid(uuid: str) -> Billing | None:
        return {
            PERSONAL_BILLING.uuid: PERSONAL_BILLING,
            ORGANIZATION_BILLING.uuid: ORGANIZATION_BILLING,
        }.get(uuid)


class FakeAuthorizationService:
    def __init__(self, roles: dict[tuple[int, int], str]) -> None:
        self.roles = roles

    def get_role_for_billing(self, user_id: int, billing: Billing) -> str | None:
        if billing.owner_type == "user" and billing.owner_id == user_id:
            return "owner"
        if billing.owner_type == "organization":
            return self.roles.get((billing.owner_id, user_id))
        return None


class FakeAuditService:
    def __init__(self) -> None:
        self.events: list[tuple[object, object, dict[str, object]]] = []

    def safe_log_for(self, actor: object, event_type: object, **kwargs: object) -> None:
        self.events.append((actor, event_type, kwargs))


class FakeServices:
    def __init__(self) -> None:
        self.roles = {(ORGANIZATION.id, USER.id): "admin"}
        self.api_key = FakeAPIKeyService()
        self.user = SimpleNamespace(get_by_id=lambda user_id: USER if user_id == USER.id else None)
        self.theme = FakeThemeService()
        self.organization = FakeOrganizationService(self.roles)
        self.billing = FakeBillingService()
        self.authorization = FakeAuthorizationService(self.roles)
        self.audit = FakeAuditService()


def _client() -> tuple[TestClient, FakeServices, object]:
    services = FakeServices()
    app = create_app()
    theme_router_registered = any(getattr(route, "path", "") == "/api/v1/themes/user" for route in app.routes)
    if not theme_router_registered and importlib.util.find_spec("rentivo.api.routes.themes") is not None:
        themes = importlib.import_module("rentivo.api.routes.themes")
        app.include_router(themes.router, prefix="/api/v1")
    app.dependency_overrides[get_services] = lambda: services
    return TestClient(app), services, app


def _bearer(secret: str = PERSONAL_SECRET) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


def _cookie_csrf(client: TestClient) -> dict[str, str]:
    principal = Principal(user=USER, api_key=LOGIN_KEY, source="web")
    token = issue_csrf_token(Response(), principal)
    client.cookies.set(settings.access_cookie_name, LOGIN_SECRET)
    client.cookies.set(settings.csrf_cookie_name, token)
    return {CSRF_HEADER_NAME: token}


def _assert_theme_response(
    body: dict,
    *,
    owner_name: str,
    stored: dict | None,
    effective: dict,
    source: str,
    can_edit: bool = True,
) -> None:
    assert body == {
        "owner_name": owner_name,
        "stored": stored,
        "effective": effective,
        "effective_source": source,
        "options": {"fonts": list(AVAILABLE_FONTS)},
        "capabilities": {
            "can_edit": can_edit,
            "can_reset": stored is not None and can_edit,
        },
    }


def _assert_theme_analytics(response: Response, scope: str) -> None:
    assert response.headers["X-Rentivo-Analytics-Event"] == "rentivo_theme_changed"
    assert response.headers["X-Rentivo-Analytics-Scope"] == scope


def _assert_no_theme_analytics(response: Response) -> None:
    assert "X-Rentivo-Analytics-Event" not in response.headers
    assert "X-Rentivo-Analytics-Scope" not in response.headers


def test_user_theme_returns_defaults_and_strict_font_options_for_new_account() -> None:
    client, _services, _app = _client()

    response = client.get("/api/v1/themes/user", headers=_bearer())

    assert response.status_code == 200
    _assert_theme_response(
        response.json(),
        owner_name="Meu Tema",
        stored=None,
        effective=DEFAULT_VALUES,
        source="default",
    )


def test_read_only_user_theme_get_disables_edit_and_reset_capabilities() -> None:
    client, services, _app = _client()
    services.theme.create_or_update_theme("user", USER.id, **THEME_PAYLOAD)

    response = client.get("/api/v1/themes/user", headers=_bearer(READ_ONLY_SECRET))

    assert response.status_code == 200
    _assert_theme_response(
        response.json(),
        owner_name="Meu Tema",
        stored=THEME_PAYLOAD,
        effective=THEME_PAYLOAD,
        source="user",
        can_edit=False,
    )


def test_read_only_organization_theme_get_disables_edit_and_reset_capabilities() -> None:
    client, services, _app = _client()
    services.theme.create_or_update_theme("organization", ORGANIZATION.id, **THEME_PAYLOAD)

    response = client.get(
        f"/api/v1/themes/organizations/{ORGANIZATION.uuid}",
        headers=_bearer(READ_ONLY_SECRET),
    )

    assert response.status_code == 200
    _assert_theme_response(
        response.json(),
        owner_name=ORGANIZATION.name,
        stored=THEME_PAYLOAD,
        effective=THEME_PAYLOAD,
        source="organization",
        can_edit=False,
    )


def test_read_only_billing_theme_get_disables_edit_and_reset_capabilities() -> None:
    client, services, _app = _client()
    services.theme.create_or_update_theme("billing", ORGANIZATION_BILLING.id, **THEME_PAYLOAD)

    response = client.get(
        f"/api/v1/themes/billings/{ORGANIZATION_BILLING.uuid}",
        headers=_bearer(READ_ONLY_SECRET),
    )

    assert response.status_code == 200
    _assert_theme_response(
        response.json(),
        owner_name=ORGANIZATION_BILLING.name,
        stored=THEME_PAYLOAD,
        effective=THEME_PAYLOAD,
        source="billing",
        can_edit=False,
    )


def test_theme_only_organization_key_reads_owner_name_without_organization_detail_scope() -> None:
    client, _services, _app = _client()
    assert THEME_SCOPES <= ORGANIZATION_KEY.scopes
    assert ORGANIZATION_GRANT in ORGANIZATION_KEY.grants
    assert APIScope.ORGANIZATIONS_READ.value not in ORGANIZATION_KEY.scopes

    response = client.get(
        f"/api/v1/themes/organizations/{ORGANIZATION.uuid}",
        headers=_bearer(ORGANIZATION_SECRET),
    )

    assert response.status_code == 200
    _assert_theme_response(
        response.json(),
        owner_name=ORGANIZATION.name,
        stored=None,
        effective=DEFAULT_VALUES,
        source="default",
    )
    assert USER.email not in response.text


def test_theme_only_organization_key_reads_billing_name_without_billing_detail_scope() -> None:
    client, _services, _app = _client()
    assert THEME_SCOPES <= ORGANIZATION_KEY.scopes
    assert ORGANIZATION_GRANT in ORGANIZATION_KEY.grants
    assert APIScope.BILLINGS_READ.value not in ORGANIZATION_KEY.scopes

    response = client.get(
        f"/api/v1/themes/billings/{ORGANIZATION_BILLING.uuid}",
        headers=_bearer(ORGANIZATION_SECRET),
    )

    assert response.status_code == 200
    _assert_theme_response(
        response.json(),
        owner_name=ORGANIZATION_BILLING.name,
        stored=None,
        effective=DEFAULT_VALUES,
        source="default",
    )
    assert USER.email not in response.text


def test_user_theme_create_records_new_state_and_integration_actor() -> None:
    client, services, _app = _client()

    response = client.put("/api/v1/themes/user", json=THEME_PAYLOAD, headers=_bearer())

    assert response.status_code == 200
    _assert_theme_response(
        response.json(),
        owner_name="Meu Tema",
        stored=THEME_PAYLOAD,
        effective=THEME_PAYLOAD,
        source="user",
    )
    _assert_theme_analytics(response, "user")
    actor, event_type, state = services.audit.events[-1]
    assert event_type == AuditEventType.THEME_CREATE
    assert actor.source == "integration"
    assert actor.api_key_uuid == PERSONAL_KEY.uuid
    assert "previous_state" not in state
    assert state["new_state"] == serialize_theme(services.theme.themes[("user", USER.id)])


def test_user_theme_update_captures_previous_state_before_service_mutation() -> None:
    client, services, _app = _client()
    existing = services.theme.create_or_update_theme("user", USER.id, **THEME_PAYLOAD)
    previous_state = serialize_theme(existing)
    updated_payload = {**THEME_PAYLOAD, "primary": "#ABCDEF"}

    response = client.put("/api/v1/themes/user", json=updated_payload, headers=_bearer())

    assert response.status_code == 200
    _assert_theme_analytics(response, "user")
    _actor, event_type, state = services.audit.events[-1]
    assert event_type == AuditEventType.THEME_UPDATE
    assert state["previous_state"] == previous_state
    assert state["new_state"]["primary"] == "#ABCDEF"


def test_user_theme_reset_records_deleted_state_and_returns_no_content() -> None:
    client, services, _app = _client()
    existing = services.theme.create_or_update_theme("user", USER.id, **THEME_PAYLOAD)

    response = client.delete("/api/v1/themes/user", headers=_bearer())

    assert response.status_code == 204
    assert response.content == b""
    _assert_no_theme_analytics(response)
    _actor, event_type, state = services.audit.events[-1]
    assert event_type == AuditEventType.THEME_DELETE
    assert state["entity_id"] == existing.id
    assert state["entity_uuid"] == existing.uuid
    assert state["previous_state"] == serialize_theme(existing)
    assert "new_state" not in state


def test_reset_without_stored_theme_is_idempotent_and_not_audited() -> None:
    client, services, _app = _client()

    response = client.delete("/api/v1/themes/user", headers=_bearer())

    assert response.status_code == 204
    _assert_no_theme_analytics(response)
    assert services.audit.events == []


def test_organization_theme_requires_admin_role() -> None:
    client, services, _app = _client()
    services.roles[(ORGANIZATION.id, USER.id)] = "manager"

    response = client.get(
        f"/api/v1/themes/organizations/{ORGANIZATION.uuid}",
        headers=_bearer(ORGANIZATION_SECRET),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_role"


def test_organization_admin_can_save_read_and_reset_theme() -> None:
    client, services, _app = _client()
    path = f"/api/v1/themes/organizations/{ORGANIZATION.uuid}"

    saved = client.put(path, json=THEME_PAYLOAD, headers=_bearer(ORGANIZATION_SECRET))
    read = client.get(path, headers=_bearer(ORGANIZATION_SECRET))
    reset = client.delete(path, headers=_bearer(ORGANIZATION_SECRET))

    assert saved.status_code == 200
    _assert_theme_analytics(saved, "organization")
    _assert_theme_response(
        saved.json(),
        owner_name=ORGANIZATION.name,
        stored=THEME_PAYLOAD,
        effective=THEME_PAYLOAD,
        source="organization",
    )
    _assert_theme_response(
        read.json(),
        owner_name=ORGANIZATION.name,
        stored=THEME_PAYLOAD,
        effective=THEME_PAYLOAD,
        source="organization",
    )
    assert reset.status_code == 204
    _assert_no_theme_analytics(reset)
    assert [event[1] for event in services.audit.events] == [
        AuditEventType.THEME_CREATE,
        AuditEventType.THEME_DELETE,
    ]


def test_organization_theme_requires_live_membership() -> None:
    client, services, _app = _client()
    del services.roles[(ORGANIZATION.id, USER.id)]

    response = client.get(
        f"/api/v1/themes/organizations/{ORGANIZATION.uuid}",
        headers=_bearer(ORGANIZATION_SECRET),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_billing_theme_requires_owner_or_admin_role() -> None:
    client, services, _app = _client()
    services.roles[(ORGANIZATION.id, USER.id)] = "manager"

    response = client.get(
        f"/api/v1/themes/billings/{ORGANIZATION_BILLING.uuid}",
        headers=_bearer(ORGANIZATION_SECRET),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_role"


def test_personal_billing_owner_can_save_and_reset_theme() -> None:
    client, services, _app = _client()
    path = f"/api/v1/themes/billings/{PERSONAL_BILLING.uuid}"

    saved = client.put(path, json=THEME_PAYLOAD, headers=_bearer())
    reset = client.delete(path, headers=_bearer())

    assert saved.status_code == 200
    _assert_theme_analytics(saved, "billing")
    _assert_theme_response(
        saved.json(),
        owner_name=PERSONAL_BILLING.name,
        stored=THEME_PAYLOAD,
        effective=THEME_PAYLOAD,
        source="billing",
    )
    assert reset.status_code == 204
    _assert_no_theme_analytics(reset)
    assert [event[1] for event in services.audit.events] == [
        AuditEventType.THEME_CREATE,
        AuditEventType.THEME_DELETE,
    ]


def test_organization_billing_admin_can_manage_theme() -> None:
    client, _services, _app = _client()
    path = f"/api/v1/themes/billings/{ORGANIZATION_BILLING.uuid}"

    saved = client.put(path, json=THEME_PAYLOAD, headers=_bearer(ORGANIZATION_SECRET))

    assert saved.status_code == 200
    _assert_theme_analytics(saved, "billing")
    _assert_theme_response(
        saved.json(),
        owner_name=ORGANIZATION_BILLING.name,
        stored=THEME_PAYLOAD,
        effective=THEME_PAYLOAD,
        source="billing",
    )


@pytest.mark.parametrize(
    ("owner_type", "owner_id", "billing", "expected_source"),
    [
        ("user", USER.id, PERSONAL_BILLING, "user"),
        ("organization", ORGANIZATION.id, ORGANIZATION_BILLING, "organization"),
    ],
)
def test_billing_theme_returns_inherited_owner_values(
    owner_type: str,
    owner_id: int,
    billing: Billing,
    expected_source: str,
) -> None:
    client, services, _app = _client()
    services.theme.create_or_update_theme(owner_type, owner_id, **THEME_PAYLOAD)
    secret = PERSONAL_SECRET if owner_type == "user" else ORGANIZATION_SECRET

    response = client.get(f"/api/v1/themes/billings/{billing.uuid}", headers=_bearer(secret))

    assert response.status_code == 200
    _assert_theme_response(
        response.json(),
        owner_name=billing.name,
        stored=None,
        effective=THEME_PAYLOAD,
        source=expected_source,
    )


def test_billing_stored_theme_takes_precedence_over_owner_theme() -> None:
    client, services, _app = _client()
    services.theme.create_or_update_theme("user", USER.id, **THEME_PAYLOAD)
    billing_payload = {**THEME_PAYLOAD, "primary": "#FEDCBA"}
    services.theme.create_or_update_theme("billing", PERSONAL_BILLING.id, **billing_payload)

    response = client.get(
        f"/api/v1/themes/billings/{PERSONAL_BILLING.uuid}",
        headers=_bearer(),
    )

    assert response.status_code == 200
    _assert_theme_response(
        response.json(),
        owner_name=PERSONAL_BILLING.name,
        stored=billing_payload,
        effective=billing_payload,
        source="billing",
    )


def test_theme_read_requires_read_scope() -> None:
    client, _services, _app = _client()

    response = client.get("/api/v1/themes/user", headers=_bearer(NO_SCOPE_SECRET))

    assert response.status_code == 403
    assert response.json()["code"] == "missing_scope"


def test_theme_write_requires_write_scope() -> None:
    client, _services, _app = _client()

    response = client.put("/api/v1/themes/user", json=THEME_PAYLOAD, headers=_bearer(READ_ONLY_SECRET))

    assert response.status_code == 403
    assert response.json()["code"] == "missing_scope"


@pytest.mark.parametrize(
    ("path", "secret"),
    [
        ("/api/v1/themes/user", NO_GRANT_SECRET),
        (f"/api/v1/themes/organizations/{ORGANIZATION.uuid}", PERSONAL_SECRET),
        (f"/api/v1/themes/billings/{ORGANIZATION_BILLING.uuid}", PERSONAL_SECRET),
    ],
)
def test_theme_resources_outside_key_grants_are_not_found(path: str, secret: str) -> None:
    client, _services, _app = _client()

    response = client.get(path, headers=_bearer(secret))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


@pytest.mark.parametrize("field", ["header_font", "text_font"])
def test_theme_update_rejects_unknown_fonts(field: str) -> None:
    client, _services, _app = _client()

    response = client.put(
        "/api/v1/themes/user",
        json={**THEME_PAYLOAD, field: "Comic Sans"},
        headers=_bearer(),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert f"body.{field}" in response.json()["fields"]


@pytest.mark.parametrize(
    "field",
    ["primary", "primary_light", "secondary", "secondary_dark", "text_color", "text_contrast"],
)
def test_theme_update_rejects_non_six_digit_hex_colors(field: str) -> None:
    client, _services, _app = _client()

    response = client.put(
        "/api/v1/themes/user",
        json={**THEME_PAYLOAD, field: "#12345G"},
        headers=_bearer(),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert f"body.{field}" in response.json()["fields"]


def test_theme_update_rejects_extra_fields() -> None:
    client, _services, _app = _client()

    response = client.put(
        "/api/v1/themes/user",
        json={**THEME_PAYLOAD, "unexpected": "value"},
        headers=_bearer(),
    )

    assert response.status_code == 422
    assert "body.unexpected" in response.json()["fields"]


def test_cookie_theme_write_requires_csrf_and_does_not_audit_failure() -> None:
    client, services, _app = _client()
    client.cookies.set(settings.access_cookie_name, LOGIN_SECRET)

    response = client.put("/api/v1/themes/user", json=THEME_PAYLOAD)

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    assert services.audit.events == []


def test_cookie_theme_write_accepts_matching_csrf_token() -> None:
    client, services, _app = _client()

    response = client.put(
        "/api/v1/themes/user",
        json=THEME_PAYLOAD,
        headers=_cookie_csrf(client),
    )

    assert response.status_code == 200
    actor, _event_type, _state = services.audit.events[-1]
    assert actor.source == "web"


def test_preview_requires_csrf_for_cookie_authentication() -> None:
    client, services, _app = _client()
    client.cookies.set(settings.access_cookie_name, LOGIN_SECRET)

    response = client.post("/api/v1/themes/preview", json=THEME_PAYLOAD)

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    assert services.audit.events == []


def test_preview_endpoint_is_sync_for_worker_thread_execution() -> None:
    themes = importlib.import_module("rentivo.api.routes.themes")

    assert inspect.iscoroutinefunction(themes.preview_theme) is False


def test_preview_returns_inline_pdf_without_audit_state() -> None:
    client, services, _app = _client()

    response = client.post("/api/v1/themes/preview", json=THEME_PAYLOAD, headers=_bearer())

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'inline; filename="theme-preview.pdf"'
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(b"%PDF")
    assert services.theme.previewed_themes == [Theme(**THEME_PAYLOAD)]
    assert services.audit.events == []


def test_preview_accepts_cookie_authentication_with_csrf() -> None:
    client, _services, _app = _client()

    response = client.post(
        "/api/v1/themes/preview",
        json=THEME_PAYLOAD,
        headers=_cookie_csrf(client),
    )

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_theme_contract_is_typed_in_openapi() -> None:
    _client_value, _services, app = _client()

    document = app.openapi()
    assert set(document["paths"]) >= {
        "/api/v1/themes/user",
        "/api/v1/themes/organizations/{org_uuid}",
        "/api/v1/themes/billings/{billing_uuid}",
        "/api/v1/themes/preview",
    }
    schemas = document["components"]["schemas"]
    update = schemas["ThemeUpdateRequest"]
    assert set(update["required"]) == set(THEME_PAYLOAD)
    assert update["additionalProperties"] is False
    assert update["properties"]["header_font"]["enum"] == list(AVAILABLE_FONTS)
    assert update["properties"]["primary"]["pattern"] == "^#[0-9A-Fa-f]{6}$"
    assert set(schemas["ThemeResponse"]["properties"]) == {
        "owner_name",
        "stored",
        "effective",
        "effective_source",
        "options",
        "capabilities",
    }
    preview_content = document["paths"]["/api/v1/themes/preview"]["post"]["responses"]["200"]["content"]
    assert preview_content == {
        "application/pdf": {"schema": {"type": "string", "format": "binary"}},
    }
