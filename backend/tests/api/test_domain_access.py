from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from rentivo.api.domain_access import (
    require_role,
    resolve_bill_access,
    resolve_billing_access,
    resolve_organization_access,
)
from rentivo.api.errors import ProblemException
from rentivo.api.principal import Principal
from rentivo.models.api_key import APIKey, APIKeyGrant
from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.organization import Organization, OrganizationMember
from rentivo.models.user import User


def _principal(*, login: bool = False) -> Principal:
    key = APIKey(
        id=1,
        uuid="login-key" if login else "integration-key",
        user_id=7,
        name="Browser" if login else "Automation",
        secret_hash=b"x" * 32,
        key_start="abcd",
        key_end="yz",
        is_login_token=login,
        scopes=frozenset({"billings:read", "bills:read", "organizations:read"}),
        grants=(APIKeyGrant(resource_type="organization", resource_id=42),),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return Principal(
        user=User(id=7, email="person@example.com"),
        api_key=key,
        source="web" if login else "integration",
    )


def _services() -> SimpleNamespace:
    return SimpleNamespace(
        api_key=MagicMock(),
        authorization=MagicMock(),
        bill=MagicMock(),
        billing=MagicMock(),
        organization=MagicMock(),
    )


def test_resolve_billing_requires_entity_grant_and_live_role() -> None:
    principal = _principal()
    services = _services()
    billing = Billing(id=9, uuid="billing-uuid", name="Aluguel", owner_type="organization", owner_id=42)
    services.billing.get_billing_by_uuid.return_value = billing
    services.api_key.can_access_resource.return_value = True
    services.authorization.get_role_for_billing.return_value = "manager"

    access = resolve_billing_access(principal, services, "billing-uuid")

    assert access.billing is billing
    assert access.principal is principal
    assert access.role == "manager"
    services.api_key.can_access_resource.assert_called_once_with(principal.api_key, "organization", 42)
    services.authorization.get_role_for_billing.assert_called_once_with(7, billing)


@pytest.mark.parametrize("failure", ["missing", "unsaved", "grant", "role"])
def test_resolve_billing_hides_every_inaccessible_resource(failure: str) -> None:
    principal = _principal()
    services = _services()
    billing = Billing(
        id=None if failure == "unsaved" else 9,
        uuid="billing-uuid",
        name="Aluguel",
        owner_type="organization",
        owner_id=42,
    )
    services.billing.get_billing_by_uuid.return_value = None if failure == "missing" else billing
    services.api_key.can_access_resource.return_value = failure != "grant"
    services.authorization.get_role_for_billing.return_value = None if failure == "role" else "viewer"

    with pytest.raises(ProblemException) as captured:
        resolve_billing_access(principal, services, "billing-uuid")

    assert captured.value.problem.status == 404
    assert captured.value.problem.code == "not_found"


def test_resolve_bill_requires_matching_parent() -> None:
    principal = _principal(login=True)
    services = _services()
    billing = Billing(id=9, uuid="billing-uuid", name="Aluguel", owner_id=7)
    services.billing.get_billing_by_uuid.return_value = billing
    services.api_key.can_access_resource.return_value = True
    services.authorization.get_role_for_billing.return_value = "owner"
    services.bill.get_bill_by_uuid.return_value = Bill(
        id=13,
        uuid="bill-uuid",
        billing_id=10,
        reference_month="2026-07",
    )

    with pytest.raises(ProblemException) as captured:
        resolve_bill_access(principal, services, "billing-uuid", "bill-uuid")

    assert captured.value.problem.status == 404


def test_resolve_bill_returns_matching_bill_and_billing_access() -> None:
    principal = _principal(login=True)
    services = _services()
    billing = Billing(id=9, uuid="billing-uuid", name="Aluguel", owner_id=7)
    bill = Bill(id=13, uuid="bill-uuid", billing_id=9, reference_month="2026-07")
    services.billing.get_billing_by_uuid.return_value = billing
    services.api_key.can_access_resource.return_value = True
    services.authorization.get_role_for_billing.return_value = "owner"
    services.bill.get_bill_by_uuid.return_value = bill

    access = resolve_bill_access(principal, services, "billing-uuid", "bill-uuid")

    assert access.bill is bill
    assert access.billing is billing
    assert access.role == "owner"


def test_resolve_organization_requires_grant_and_live_member() -> None:
    principal = _principal()
    services = _services()
    organization = Organization(id=42, uuid="org-uuid", name="Acme")
    member = OrganizationMember(organization_id=42, user_id=7, role="admin")
    services.organization.get_by_uuid.return_value = organization
    services.organization.get_member.return_value = member
    services.api_key.can_access_resource.return_value = True

    access = resolve_organization_access(principal, services, "org-uuid")

    assert access.organization is organization
    assert access.member is member
    assert access.role == "admin"
    services.organization.get_member.assert_called_once_with(42, 7)


@pytest.mark.parametrize("failure", ["missing", "unsaved", "grant", "member"])
def test_resolve_organization_hides_every_inaccessible_resource(failure: str) -> None:
    principal = _principal()
    services = _services()
    organization = Organization(id=None if failure == "unsaved" else 42, uuid="org-uuid", name="Acme")
    services.organization.get_by_uuid.return_value = None if failure == "missing" else organization
    services.api_key.can_access_resource.return_value = failure != "grant"
    services.organization.get_member.return_value = (
        None if failure == "member" else OrganizationMember(organization_id=42, user_id=7, role="viewer")
    )

    with pytest.raises(ProblemException) as captured:
        resolve_organization_access(principal, services, "org-uuid")

    assert captured.value.problem.status == 404


def test_require_role_accepts_allowed_role_and_rejects_other_roles() -> None:
    assert require_role("manager", {"owner", "admin", "manager"}) is None

    with pytest.raises(ProblemException) as captured:
        require_role("manager", {"owner", "admin"})

    assert captured.value.problem.status == 403
    assert captured.value.problem.code == "insufficient_role"
