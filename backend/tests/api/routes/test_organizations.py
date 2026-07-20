from __future__ import annotations

import importlib.util
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
from rentivo.constants.api_scopes import ALL_FIRST_PARTY_SCOPES, APIScope
from rentivo.models.api_key import APIKey, APIKeyGrant
from rentivo.models.billing import Billing
from rentivo.models.invite import Invite
from rentivo.models.organization import Organization, OrganizationMember
from rentivo.models.user import User
from rentivo.services.billing_stats import BillingStats
from rentivo.settings import settings

NOW = datetime(2026, 7, 18, 12, tzinfo=UTC)
LOGIN_SECRET = f"rntv-v1-{'L' * 43}"
INTEGRATION_SECRET = f"rntv-v1-{'I' * 43}"
USER = User(id=7, email="admin@example.com")
TARGET_USER = User(id=8, email="member@example.com")
OTHER_USER = User(id=9, email="other@example.com")
ORGANIZATION = Organization(
    id=31,
    uuid="01JORG00000000000000000000",
    name="Acme Imoveis",
    created_by=USER.id,
    enforce_mfa=False,
    pix_key="admin@example.com",
    pix_merchant_name="Acme",
    pix_merchant_city="Salvador",
    created_at=NOW - timedelta(days=10),
    updated_at=NOW - timedelta(days=1),
)
SECOND_ORGANIZATION = Organization(
    id=32,
    uuid="01JORG00000000000000000001",
    name="Beta Imoveis",
    created_by=USER.id,
    created_at=NOW - timedelta(days=5),
    updated_at=NOW,
)
PERSONAL_BILLING = Billing(
    id=51,
    uuid="01JBILLING0000000000000000",
    name="Apartamento 101",
    owner_type="user",
    owner_id=USER.id,
)
ORGANIZATION_BILLING = Billing(
    id=52,
    uuid="01JORGBILLING00000000000000",
    name="Apartamento 201",
    owner_type="organization",
    owner_id=ORGANIZATION.id,
)
SECOND_ORGANIZATION_BILLING = Billing(
    id=53,
    uuid="01JORGBILLING00000000000001",
    name="Apartamento 301",
    owner_type="organization",
    owner_id=SECOND_ORGANIZATION.id,
)


def _api_key(
    *,
    key_id: int,
    uuid: str,
    is_login_token: bool,
    scopes: frozenset[str],
    grants: tuple[APIKeyGrant, ...] = (),
) -> APIKey:
    return APIKey(
        id=key_id,
        uuid=uuid,
        user_id=USER.id,
        name="Browser" if is_login_token else "Integration",
        secret_hash=bytes([key_id]) * 32,
        key_start="abcd",
        key_end="yz",
        is_login_token=is_login_token,
        scopes=scopes,
        grants=grants,
        expires_at=NOW + timedelta(days=30),
    )


LOGIN_KEY = _api_key(
    key_id=1,
    uuid="01JLOGIN0000000000000000000",
    is_login_token=True,
    scopes=ALL_FIRST_PARTY_SCOPES,
)
INTEGRATION_KEY = _api_key(
    key_id=2,
    uuid="01JINTEGRATION0000000000000",
    is_login_token=False,
    # Privileged scopes are deliberately present to prove the token-class gate
    # still blocks a manually constructed integration key.
    scopes=frozenset(
        {
            APIScope.ORGANIZATIONS_READ.value,
            APIScope.ORGANIZATIONS_WRITE.value,
            APIScope.ORGANIZATIONS_MEMBERS.value,
        }
    ),
    grants=(APIKeyGrant(resource_type="organization", resource_id=ORGANIZATION.id),),
)


class FakeAPIKeyService:
    def __init__(self, organization: FakeOrganizationService) -> None:
        self.organization = organization
        self.credentials = {
            LOGIN_SECRET: LOGIN_KEY,
            INTEGRATION_SECRET: INTEGRATION_KEY,
        }

    def authenticate(self, secret: str) -> APIKey | None:
        return self.credentials.get(secret)

    def can_access_resource(self, key: APIKey, resource_type: str, resource_id: int) -> bool:
        if resource_type == "user":
            return resource_id == key.user_id and (
                key.is_login_token or APIKeyGrant(resource_type="user", resource_id=resource_id) in key.grants
            )
        if resource_type != "organization":
            return False
        member = self.organization.get_member(resource_id, key.user_id)
        if member is None:
            return False
        return key.is_login_token or APIKeyGrant(resource_type="organization", resource_id=resource_id) in key.grants


class FakeUserService:
    def get_by_id(self, user_id: int) -> User | None:
        return {USER.id: USER, TARGET_USER.id: TARGET_USER, OTHER_USER.id: OTHER_USER}.get(user_id)


class FakeOrganizationService:
    def __init__(self) -> None:
        self.organizations = {
            ORGANIZATION.uuid: ORGANIZATION.model_copy(deep=True),
            SECOND_ORGANIZATION.uuid: SECOND_ORGANIZATION.model_copy(deep=True),
        }
        self.members: dict[tuple[int, int], OrganizationMember] = {
            (ORGANIZATION.id, USER.id): OrganizationMember(
                id=1,
                organization_id=ORGANIZATION.id,
                user_id=USER.id,
                email=USER.email,
                role="admin",
                created_at=NOW - timedelta(days=10),
            ),
            (ORGANIZATION.id, TARGET_USER.id): OrganizationMember(
                id=2,
                organization_id=ORGANIZATION.id,
                user_id=TARGET_USER.id,
                email=TARGET_USER.email,
                role="viewer",
                created_at=NOW - timedelta(days=2),
            ),
            (SECOND_ORGANIZATION.id, USER.id): OrganizationMember(
                id=3,
                organization_id=SECOND_ORGANIZATION.id,
                user_id=USER.id,
                email=USER.email,
                role="admin",
                created_at=NOW - timedelta(days=5),
            ),
        }
        self.created_names: list[tuple[str, int]] = []
        self.updated: list[Organization] = []
        self.deleted_ids: list[int] = []
        self.role_updates: list[tuple[int, int, str]] = []
        self.removals: list[tuple[int, int]] = []
        self.remove_attempts: list[tuple[int, int, str | None]] = []
        self.remove_result = True
        self.mfa_updates: list[tuple[int, bool]] = []
        self.update_error: ValueError | None = None

    def list_user_organizations(self, user_id: int) -> list[Organization]:
        return [
            organization
            for organization in self.organizations.values()
            if organization.id is not None and self.get_member(organization.id, user_id) is not None
        ]

    def get_by_uuid(self, uuid: str) -> Organization | None:
        return self.organizations.get(uuid)

    def get_by_id(self, org_id: int) -> Organization | None:
        return next((organization for organization in self.organizations.values() if organization.id == org_id), None)

    def get_member(self, org_id: int, user_id: int) -> OrganizationMember | None:
        return self.members.get((org_id, user_id))

    def list_members(self, org_id: int) -> list[OrganizationMember]:
        return [member for (member_org_id, _user_id), member in self.members.items() if member_org_id == org_id]

    def create_organization(self, name: str, created_by: int) -> Organization:
        self.created_names.append((name, created_by))
        organization = Organization(
            id=99,
            uuid="01JCREATEDORG0000000000000",
            name=name,
            created_by=created_by,
            created_at=NOW,
            updated_at=NOW,
        )
        self.organizations[organization.uuid] = organization
        self.members[(organization.id, created_by)] = OrganizationMember(
            organization_id=organization.id,
            user_id=created_by,
            email=USER.email,
            role="admin",
            created_at=NOW,
        )
        return organization

    def update_organization(self, organization: Organization) -> Organization:
        if self.update_error is not None:
            raise self.update_error
        self.updated.append(organization.model_copy(deep=True))
        return organization

    def delete_organization(self, org_id: int) -> None:
        self.deleted_ids.append(org_id)

    def update_member_role(self, org_id: int, user_id: int, role: str) -> None:
        self.role_updates.append((org_id, user_id, role))
        self.members[(org_id, user_id)].role = role

    def remove_member(self, org_id: int, user_id: int, *, expected_role: str | None = None) -> bool:
        self.remove_attempts.append((org_id, user_id, expected_role))
        if not self.remove_result:
            return False
        self.removals.append((org_id, user_id))
        self.members.pop((org_id, user_id), None)
        return True

    def set_enforce_mfa(self, org_id: int, enforce: bool) -> Organization:
        self.mfa_updates.append((org_id, enforce))
        organization = self.get_by_id(org_id)
        assert organization is not None
        organization.enforce_mfa = enforce
        return organization


class FakeInviteService:
    def __init__(self) -> None:
        self.invites = [
            Invite(
                id=71,
                uuid="01JINVITE0000000000000000",
                organization_id=ORGANIZATION.id,
                organization_name=ORGANIZATION.name,
                invited_user_id=TARGET_USER.id,
                invited_email=TARGET_USER.email,
                invited_by_user_id=USER.id,
                invited_by_email=USER.email,
                role="viewer",
                status="pending",
                created_at=NOW,
            )
        ]
        self.send_error: ValueError | None = None
        self.send_calls: list[tuple[int, str, str, int]] = []
        self.response_conflict = False

    def list_pending(self, user_id: int) -> list[Invite]:
        return [invite for invite in self.invites if invite.invited_user_id == user_id and invite.status == "pending"]

    def list_org_invites(self, org_id: int) -> list[Invite]:
        return [invite for invite in self.invites if invite.organization_id == org_id]

    def get_pending_invite(self, invite_uuid: str, user_id: int, *, action: str) -> Invite:
        return self._pending_invite(invite_uuid, user_id, action=action)

    def send_invite(self, org_id: int, email: str, role: str, invited_by_user_id: int) -> Invite:
        self.send_calls.append((org_id, email, role, invited_by_user_id))
        if self.send_error is not None:
            raise self.send_error
        invite = Invite(
            id=72,
            uuid="01JINVITECREATED00000000000",
            organization_id=org_id,
            organization_name=ORGANIZATION.name,
            invited_user_id=TARGET_USER.id,
            invited_email=email,
            invited_by_user_id=invited_by_user_id,
            invited_by_email=USER.email,
            role=role,
            status="pending",
            created_at=NOW,
        )
        self.invites.append(invite)
        return invite

    def accept_invite(self, invite: Invite) -> Invite:
        if self.response_conflict:
            raise ValueError("Invite is no longer pending")
        invite.status = "accepted"
        invite.responded_at = NOW
        return invite

    def decline_invite(self, invite: Invite) -> Invite:
        if self.response_conflict:
            raise ValueError("Invite is no longer pending")
        invite.status = "declined"
        invite.responded_at = NOW
        return invite

    def _pending_invite(self, invite_uuid: str, user_id: int, *, action: str) -> Invite:
        invite = next((candidate for candidate in self.invites if candidate.uuid == invite_uuid), None)
        if invite is None:
            raise ValueError("Invite not found")
        if invite.invited_user_id != user_id:
            raise ValueError(f"Not authorized to {action} this invite")
        if invite.status != "pending":
            raise ValueError("Invite is no longer pending")
        return invite


class FakeAuditService:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def safe_log_for(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


class FakeJobService:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, str, dict[str, Any]]] = []

    def enqueue_for(self, actor: Any, job_type: str, payload: dict[str, Any]) -> None:
        self.calls.append((actor, job_type, payload))


class FakeMFAService:
    def __init__(self) -> None:
        self.has_mfa = False
        self.requires_setup = False
        self.requires_setup_results: list[bool] = []
        self.requires_setup_calls: list[int] = []

    def has_any_mfa(self, user_id: int) -> bool:
        assert user_id == USER.id
        return self.has_mfa

    def user_requires_mfa_setup(self, user_id: int) -> bool:
        self.requires_setup_calls.append(user_id)
        if self.requires_setup_results:
            return self.requires_setup_results.pop(0)
        return self.requires_setup


class FakeBillingService:
    def __init__(self) -> None:
        self.billing = PERSONAL_BILLING.model_copy(deep=True)
        self.billings = [
            self.billing,
            ORGANIZATION_BILLING.model_copy(deep=True),
            SECOND_ORGANIZATION_BILLING.model_copy(deep=True),
        ]
        self.transfer_error: ValueError | None = None
        self.transfer_calls: list[tuple[int, int, int | None]] = []

    def list_billings_for_user(self, user_id: int) -> list[Billing]:
        assert user_id == USER.id
        return self.billings

    def get_billing_by_uuid(self, uuid: str) -> Billing | None:
        return self.billing if uuid == self.billing.uuid else None

    def transfer_to_organization(
        self,
        billing_id: int,
        org_id: int,
        *,
        expected_owner_id: int | None = None,
    ) -> None:
        if self.transfer_error is not None:
            raise self.transfer_error
        self.transfer_calls.append((billing_id, org_id, expected_owner_id))
        self.billing.owner_type = "organization"
        self.billing.owner_id = org_id


class FakeAuthorizationService:
    @staticmethod
    def can_transfer_billing(user_id: int, billing: Billing) -> bool:
        return billing.owner_type == "user" and billing.owner_id == user_id


class FakeBillingNotificationService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def notify_transferred(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class FakeBillingStatsService:
    def __init__(self) -> None:
        self.calls: list[list[int]] = []

    def stats_for_ids(self, billing_ids: list[int]) -> BillingStats:
        self.calls.append(billing_ids)
        return BillingStats(
            year=2026,
            expected=460000,
            received=180000,
            pending=200000,
            overdue=80000,
            paid_count=2,
            pending_count=2,
            overdue_count=1,
            total_expenses=30000,
            net_income=150000,
        )


@dataclass(slots=True)
class OrganizationHarness:
    client: TestClient
    app: Any
    services: Any
    organization: FakeOrganizationService
    invite: FakeInviteService
    audit: FakeAuditService
    job: FakeJobService
    mfa: FakeMFAService
    billing: FakeBillingService
    billing_stats: FakeBillingStatsService
    billing_notification: FakeBillingNotificationService


def _mount_domain_routers(app: Any) -> None:
    if importlib.util.find_spec("rentivo.api.routes.organizations") is None:
        return
    from rentivo.api.routes.invites import router as invites_router
    from rentivo.api.routes.organizations import router as organizations_router

    app.include_router(organizations_router, prefix="/api/v1")
    app.include_router(invites_router, prefix="/api/v1")


def build_organization_harness(monkeypatch: pytest.MonkeyPatch) -> OrganizationHarness:
    monkeypatch.setattr(settings, "secret_key", "organization-route-contract-signing-key")
    monkeypatch.setattr(settings, "access_cookie_name", "__Host-rentivo_access")
    monkeypatch.setattr(settings, "csrf_cookie_name", "__Host-rentivo_csrf")
    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(settings, "public_app_url", "https://rentivo.test")

    organization = FakeOrganizationService()
    invite = FakeInviteService()
    audit = FakeAuditService()
    job = FakeJobService()
    mfa = FakeMFAService()
    billing = FakeBillingService()
    billing_stats = FakeBillingStatsService()
    billing_notification = FakeBillingNotificationService()
    services = SimpleNamespace(
        api_key=FakeAPIKeyService(organization),
        user=FakeUserService(),
        organization=organization,
        invite=invite,
        audit=audit,
        job=job,
        mfa=mfa,
        billing=billing,
        billing_stats=billing_stats,
        authorization=FakeAuthorizationService(),
        billing_notification=billing_notification,
    )
    app = create_app()
    _mount_domain_routers(app)
    app.dependency_overrides[get_services] = lambda: services
    return OrganizationHarness(
        client=TestClient(app),
        app=app,
        services=services,
        organization=organization,
        invite=invite,
        audit=audit,
        job=job,
        mfa=mfa,
        billing=billing,
        billing_stats=billing_stats,
        billing_notification=billing_notification,
    )


@pytest.fixture()
def organization_harness(monkeypatch: pytest.MonkeyPatch) -> OrganizationHarness:
    return build_organization_harness(monkeypatch)


def login_headers(*, csrf: bool) -> dict[str, str]:
    cookie = f"{settings.access_cookie_name}={LOGIN_SECRET}"
    headers = {"Cookie": cookie}
    if csrf:
        token = issue_csrf_token(Response(), Principal(user=USER, api_key=LOGIN_KEY, source="web"))
        headers["Cookie"] = f"{cookie}; {settings.csrf_cookie_name}={token}"
        headers[CSRF_HEADER_NAME] = token
    return headers


def integration_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {INTEGRATION_SECRET}"}


def test_new_user_lists_no_organizations(organization_harness: OrganizationHarness) -> None:
    organization_harness.organization.members.clear()

    response = organization_harness.client.get("/api/v1/organizations", headers=login_headers(csrf=False))

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_organization_list_filters_integration_grants_without_disclosing_internal_ids(
    organization_harness: OrganizationHarness,
) -> None:
    response = organization_harness.client.get(
        "/api/v1/organizations",
        headers=integration_headers(),
    )

    assert response.status_code == 200
    assert [item["uuid"] for item in response.json()["items"]] == [ORGANIZATION.uuid]
    assert '"id":' not in response.text
    assert SECOND_ORGANIZATION.name not in response.text


def test_organization_detail_returns_live_members_and_backend_capabilities(
    organization_harness: OrganizationHarness,
) -> None:
    response = organization_harness.client.get(
        f"/api/v1/organizations/{ORGANIZATION.uuid}",
        headers=login_headers(csrf=False),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["uuid"] == ORGANIZATION.uuid
    assert payload["current_role"] == "admin"
    assert payload["capabilities"] == {
        "can_manage": True,
        "can_invite": True,
        "can_create_billing": True,
        "can_view_billing_stats": True,
    }
    assert payload["stats"] == {
        "year": 2026,
        "expected": 460000,
        "received": 180000,
        "pending": 200000,
        "overdue": 80000,
        "paid_count": 2,
        "pending_count": 2,
        "overdue_count": 1,
        "active_count": 3,
        "billed_count": 5,
        "total_expenses": 30000,
        "net_income": 150000,
    }
    assert organization_harness.billing_stats.calls == [[ORGANIZATION_BILLING.id]]
    assert payload["settings"] == {
        "pix_key": ORGANIZATION.pix_key,
        "pix_merchant_name": ORGANIZATION.pix_merchant_name,
        "pix_merchant_city": ORGANIZATION.pix_merchant_city,
    }
    assert {member["email"] for member in payload["members"]} == {USER.email, TARGET_USER.email}
    assert payload["members"][0]["is_current_user"] is True
    assert payload["invites"][0]["invited_email"] == TARGET_USER.email
    assert "organization_id" not in response.text


def test_integration_detail_is_read_only_and_omits_settings_and_sent_invites(
    organization_harness: OrganizationHarness,
) -> None:
    response = organization_harness.client.get(
        f"/api/v1/organizations/{ORGANIZATION.uuid}",
        headers=integration_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "uuid": ORGANIZATION.uuid,
        "name": ORGANIZATION.name,
        "enforce_mfa": False,
        "current_role": "admin",
        "capabilities": {
            "can_manage": False,
            "can_invite": False,
            "can_create_billing": False,
            "can_view_billing_stats": False,
        },
        "stats": None,
        "created_at": ORGANIZATION.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": ORGANIZATION.updated_at.isoformat().replace("+00:00", "Z"),
    }
    assert USER.email not in response.text
    assert TARGET_USER.email not in response.text
    assert '"user_id"' not in response.text
    assert organization_harness.billing_stats.calls == []


def test_integration_detail_includes_stats_only_with_explicit_billing_read_scope(
    organization_harness: OrganizationHarness,
) -> None:
    key = INTEGRATION_KEY.model_copy(update={"scopes": INTEGRATION_KEY.scopes | {APIScope.BILLINGS_READ.value}})
    organization_harness.services.api_key.credentials[INTEGRATION_SECRET] = key

    response = organization_harness.client.get(
        f"/api/v1/organizations/{ORGANIZATION.uuid}",
        headers=integration_headers(),
    )

    assert response.status_code == 200
    assert response.json()["capabilities"]["can_view_billing_stats"] is True
    assert response.json()["stats"]["expected"] == 460000
    assert organization_harness.billing_stats.calls == [[ORGANIZATION_BILLING.id]]


def test_organization_detail_requires_both_grant_and_live_membership(
    organization_harness: OrganizationHarness,
) -> None:
    ungranted = organization_harness.client.get(
        f"/api/v1/organizations/{SECOND_ORGANIZATION.uuid}",
        headers=integration_headers(),
    )
    organization_harness.organization.members.pop((ORGANIZATION.id, USER.id))
    stale = organization_harness.client.get(
        f"/api/v1/organizations/{ORGANIZATION.uuid}",
        headers=integration_headers(),
    )

    assert ungranted.status_code == 404
    assert ungranted.json()["code"] == "not_found"
    assert stale.status_code == 404
    assert stale.json()["code"] == "not_found"


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/v1/organizations", {"name": "   "}),
        ("patch", f"/api/v1/organizations/{ORGANIZATION.uuid}", {}),
        ("patch", f"/api/v1/organizations/{ORGANIZATION.uuid}", {"name": None}),
        (
            "post",
            f"/api/v1/organizations/{ORGANIZATION.uuid}/invites",
            {"email": "invalid", "role": "viewer"},
        ),
        (
            "post",
            f"/api/v1/organizations/{ORGANIZATION.uuid}/invites",
            {"email": "member@example.com@attacker.test", "role": "viewer"},
        ),
        (
            "post",
            f"/api/v1/organizations/{ORGANIZATION.uuid}/invites",
            {"email": "@example.com", "role": "viewer"},
        ),
        (
            "post",
            f"/api/v1/organizations/{ORGANIZATION.uuid}/billing-transfers",
            {"billing_uuid": "   "},
        ),
    ],
)
def test_organization_mutations_reject_invalid_strict_payloads(
    organization_harness: OrganizationHarness,
    method: str,
    path: str,
    payload: dict[str, Any],
) -> None:
    response = organization_harness.client.request(
        method,
        path,
        json=payload,
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/v1/organizations", {"name": "Nova"}),
        ("patch", f"/api/v1/organizations/{ORGANIZATION.uuid}", {"name": "Nova"}),
        ("delete", f"/api/v1/organizations/{ORGANIZATION.uuid}", None),
        ("patch", f"/api/v1/organizations/{ORGANIZATION.uuid}/members/{TARGET_USER.id}", {"role": "manager"}),
        ("delete", f"/api/v1/organizations/{ORGANIZATION.uuid}/members/{TARGET_USER.id}", None),
        (
            "post",
            f"/api/v1/organizations/{ORGANIZATION.uuid}/invites",
            {"email": TARGET_USER.email, "role": "viewer"},
        ),
        ("put", f"/api/v1/organizations/{ORGANIZATION.uuid}/mfa-policy", {"enforce_mfa": True}),
        (
            "post",
            f"/api/v1/organizations/{ORGANIZATION.uuid}/billing-transfers",
            {"billing_uuid": PERSONAL_BILLING.uuid},
        ),
    ],
)
def test_organization_mutations_reject_bearer_integration_keys(
    organization_harness: OrganizationHarness,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    response = organization_harness.client.request(method, path, json=payload, headers=integration_headers())

    assert response.status_code == 403
    assert response.json()["code"] == "login_token_required"


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/v1/organizations", {"name": "Nova"}),
        ("patch", f"/api/v1/organizations/{ORGANIZATION.uuid}", {"name": "Nova"}),
        ("delete", f"/api/v1/organizations/{ORGANIZATION.uuid}", None),
        ("patch", f"/api/v1/organizations/{ORGANIZATION.uuid}/members/{TARGET_USER.id}", {"role": "manager"}),
        ("delete", f"/api/v1/organizations/{ORGANIZATION.uuid}/members/{TARGET_USER.id}", None),
        (
            "post",
            f"/api/v1/organizations/{ORGANIZATION.uuid}/invites",
            {"email": TARGET_USER.email, "role": "viewer"},
        ),
        ("put", f"/api/v1/organizations/{ORGANIZATION.uuid}/mfa-policy", {"enforce_mfa": True}),
        (
            "post",
            f"/api/v1/organizations/{ORGANIZATION.uuid}/billing-transfers",
            {"billing_uuid": PERSONAL_BILLING.uuid},
        ),
    ],
)
def test_cookie_organization_mutations_require_csrf(
    organization_harness: OrganizationHarness,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    response = organization_harness.client.request(method, path, json=payload, headers=login_headers(csrf=False))

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("patch", f"/api/v1/organizations/{ORGANIZATION.uuid}", {"name": "Nova"}),
        ("delete", f"/api/v1/organizations/{ORGANIZATION.uuid}", None),
        ("patch", f"/api/v1/organizations/{ORGANIZATION.uuid}/members/{TARGET_USER.id}", {"role": "manager"}),
        ("delete", f"/api/v1/organizations/{ORGANIZATION.uuid}/members/{TARGET_USER.id}", None),
        (
            "post",
            f"/api/v1/organizations/{ORGANIZATION.uuid}/invites",
            {"email": TARGET_USER.email, "role": "viewer"},
        ),
        ("put", f"/api/v1/organizations/{ORGANIZATION.uuid}/mfa-policy", {"enforce_mfa": True}),
        (
            "post",
            f"/api/v1/organizations/{ORGANIZATION.uuid}/billing-transfers",
            {"billing_uuid": PERSONAL_BILLING.uuid},
        ),
    ],
)
def test_organization_management_requires_current_admin_role(
    organization_harness: OrganizationHarness,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    organization_harness.organization.members[(ORGANIZATION.id, USER.id)].role = "manager"

    response = organization_harness.client.request(method, path, json=payload, headers=login_headers(csrf=True))

    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_role"


def test_create_organization_normalizes_name_and_audits(organization_harness: OrganizationHarness) -> None:
    response = organization_harness.client.post(
        "/api/v1/organizations",
        json={"name": "  Nova Administradora  "},
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Nova Administradora"
    assert response.json()["current_role"] == "admin"
    assert response.headers["X-Rentivo-Analytics-Event"] == "rentivo_organization_created"
    assert organization_harness.organization.created_names == [("Nova Administradora", USER.id)]
    assert organization_harness.audit.calls[-1][0][1] == "organization.create"
    assert organization_harness.job.calls == []


def test_patch_organization_replaces_only_supplied_settings_and_audits(
    organization_harness: OrganizationHarness,
) -> None:
    response = organization_harness.client.patch(
        f"/api/v1/organizations/{ORGANIZATION.uuid}",
        json={"name": "  Acme Atualizada  ", "pix_merchant_city": "  Recife  "},
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 200
    updated = organization_harness.organization.updated[-1]
    assert updated.name == "Acme Atualizada"
    assert updated.pix_key == ORGANIZATION.pix_key
    assert updated.pix_merchant_city == "Recife"
    audit = organization_harness.audit.calls[-1]
    assert audit[0][1] == "organization.update"
    assert audit[1]["previous_state"]["name"] == ORGANIZATION.name
    assert audit[1]["new_state"]["name"] == "Acme Atualizada"


def test_patch_organization_maps_invalid_pix_to_validation_problem(
    organization_harness: OrganizationHarness,
) -> None:
    organization_harness.organization.update_error = ValueError("invalid pix")

    response = organization_harness.client.patch(
        f"/api/v1/organizations/{ORGANIZATION.uuid}",
        json={"pix_key": "invalid"},
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert organization_harness.audit.calls == []


def test_delete_organization_audits_before_returning_no_content(
    organization_harness: OrganizationHarness,
) -> None:
    response = organization_harness.client.delete(
        f"/api/v1/organizations/{ORGANIZATION.uuid}",
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 204
    assert organization_harness.organization.deleted_ids == [ORGANIZATION.id]
    assert organization_harness.audit.calls[-1][0][1] == "organization.delete"


def test_update_member_role_audits_and_queues_notification(organization_harness: OrganizationHarness) -> None:
    response = organization_harness.client.patch(
        f"/api/v1/organizations/{ORGANIZATION.uuid}/members/{TARGET_USER.id}",
        json={"role": "manager"},
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "manager"
    assert organization_harness.organization.role_updates == [(ORGANIZATION.id, TARGET_USER.id, "manager")]
    assert organization_harness.audit.calls[-1][0][1] == "organization.update_member_role"
    assert organization_harness.job.calls[-1][2]["event"] == "member_changed"
    assert organization_harness.job.calls[-1][2]["to_email"] == TARGET_USER.email


def test_update_missing_member_is_conflict_without_side_effects(organization_harness: OrganizationHarness) -> None:
    response = organization_harness.client.patch(
        f"/api/v1/organizations/{ORGANIZATION.uuid}/members/404",
        json={"role": "manager"},
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "membership_conflict"
    assert organization_harness.audit.calls == []
    assert organization_harness.job.calls == []


def test_remove_member_audits_and_self_removal_conflicts(organization_harness: OrganizationHarness) -> None:
    success = organization_harness.client.delete(
        f"/api/v1/organizations/{ORGANIZATION.uuid}/members/{TARGET_USER.id}",
        headers=login_headers(csrf=True),
    )
    conflict = organization_harness.client.delete(
        f"/api/v1/organizations/{ORGANIZATION.uuid}/members/{USER.id}",
        headers=login_headers(csrf=True),
    )

    assert success.status_code == 204
    assert organization_harness.organization.removals == [(ORGANIZATION.id, TARGET_USER.id)]
    assert organization_harness.audit.calls[-1][0][1] == "organization.remove_member"
    assert organization_harness.job.calls == []
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "membership_conflict"


def test_remove_missing_member_is_conflict_without_side_effects(organization_harness: OrganizationHarness) -> None:
    response = organization_harness.client.delete(
        f"/api/v1/organizations/{ORGANIZATION.uuid}/members/404",
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "membership_conflict"
    assert organization_harness.organization.removals == []
    assert organization_harness.audit.calls == []


def test_remove_member_maps_conditional_delete_race_to_conflict(
    organization_harness: OrganizationHarness,
) -> None:
    organization_harness.organization.remove_result = False

    response = organization_harness.client.delete(
        f"/api/v1/organizations/{ORGANIZATION.uuid}/members/{TARGET_USER.id}",
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "membership_conflict"
    assert organization_harness.organization.remove_attempts == [(ORGANIZATION.id, TARGET_USER.id, "viewer")]
    assert organization_harness.organization.removals == []
    assert organization_harness.audit.calls == []


def test_invite_creation_normalizes_email_and_preserves_audit_and_email_side_effects(
    organization_harness: OrganizationHarness,
) -> None:
    response = organization_harness.client.post(
        f"/api/v1/organizations/{ORGANIZATION.uuid}/invites",
        json={"email": "  MEMBER@EXAMPLE.COM  ", "role": "manager"},
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 201
    assert response.headers["X-Rentivo-Analytics-Event"] == "rentivo_invite_sent"
    assert response.json()["invited_email"] == TARGET_USER.email
    assert organization_harness.invite.send_calls == [(ORGANIZATION.id, TARGET_USER.email, "manager", USER.id)]
    assert organization_harness.audit.calls[-1][0][1] == "invite.send"
    payload = organization_harness.job.calls[-1][2]
    assert payload["event"] == "invite_received"
    assert payload["to_email"] == TARGET_USER.email
    assert payload["ctx"]["invites_url"] == "https://rentivo.test/invites/"


def test_duplicate_invite_is_generic_conflict_without_audit_or_email(
    organization_harness: OrganizationHarness,
) -> None:
    organization_harness.invite.send_error = ValueError("already has a pending invite")

    response = organization_harness.client.post(
        f"/api/v1/organizations/{ORGANIZATION.uuid}/invites",
        json={"email": TARGET_USER.email, "role": "viewer"},
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "invite_conflict"
    assert TARGET_USER.email not in response.json()["detail"]
    assert organization_harness.audit.calls == []
    assert organization_harness.job.calls == []


def test_mfa_policy_update_audits_and_reports_required_bootstrap(
    organization_harness: OrganizationHarness,
) -> None:
    response = organization_harness.client.put(
        f"/api/v1/organizations/{ORGANIZATION.uuid}/mfa-policy",
        json={"enforce_mfa": True},
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 200
    assert response.json() == {"enforce_mfa": True, "mfa_setup_required": True}
    assert organization_harness.organization.mfa_updates == [(ORGANIZATION.id, True)]
    assert organization_harness.audit.calls[-1][0][1] == "organization.update_mfa"
    assert organization_harness.job.calls == []


def test_billing_transfer_requires_personal_access_and_preserves_side_effects(
    organization_harness: OrganizationHarness,
) -> None:
    hidden_billing = organization_harness.billing.billing.model_copy(update={"owner_id": OTHER_USER.id})
    organization_harness.billing.billing = hidden_billing
    denied = organization_harness.client.post(
        f"/api/v1/organizations/{ORGANIZATION.uuid}/billing-transfers",
        json={"billing_uuid": hidden_billing.uuid},
        headers=login_headers(csrf=True),
    )
    organization_harness.billing.billing = PERSONAL_BILLING.model_copy(deep=True)

    success = organization_harness.client.post(
        f"/api/v1/organizations/{ORGANIZATION.uuid}/billing-transfers",
        json={"billing_uuid": PERSONAL_BILLING.uuid},
        headers=login_headers(csrf=True),
    )

    assert denied.status_code == 404
    assert denied.json()["code"] == "not_found"
    assert success.status_code == 200
    assert success.json() == {"billing_uuid": PERSONAL_BILLING.uuid, "organization_uuid": ORGANIZATION.uuid}
    assert organization_harness.billing.transfer_calls == [(PERSONAL_BILLING.id, ORGANIZATION.id, USER.id)]
    assert organization_harness.audit.calls[-1][0][1] == "billing.transfer"
    notification = organization_harness.billing_notification.calls[-1]
    assert notification["previous_owner"] == {"owner_type": "user", "owner_id": USER.id}
    assert notification["actor_user_id"] == USER.id


def test_billing_transfer_conflict_has_no_audit_or_notification(
    organization_harness: OrganizationHarness,
) -> None:
    organization_harness.billing.transfer_error = ValueError("already transferred")

    response = organization_harness.client.post(
        f"/api/v1/organizations/{ORGANIZATION.uuid}/billing-transfers",
        json={"billing_uuid": PERSONAL_BILLING.uuid},
        headers=login_headers(csrf=True),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "billing_transfer_conflict"
    assert organization_harness.audit.calls == []
    assert organization_harness.billing_notification.calls == []


def test_billing_transfer_hides_missing_and_nonpersonal_billings(
    organization_harness: OrganizationHarness,
) -> None:
    missing = organization_harness.client.post(
        f"/api/v1/organizations/{ORGANIZATION.uuid}/billing-transfers",
        json={"billing_uuid": "missing"},
        headers=login_headers(csrf=True),
    )
    organization_harness.billing.billing.owner_type = "organization"
    organization_harness.billing.billing.owner_id = ORGANIZATION.id
    nonpersonal = organization_harness.client.post(
        f"/api/v1/organizations/{ORGANIZATION.uuid}/billing-transfers",
        json={"billing_uuid": PERSONAL_BILLING.uuid},
        headers=login_headers(csrf=True),
    )

    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"
    assert nonpersonal.status_code == 404
    assert nonpersonal.json()["code"] == "not_found"
    assert organization_harness.billing.transfer_calls == []
