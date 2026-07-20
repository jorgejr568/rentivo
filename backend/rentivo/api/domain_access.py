from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from rentivo.api.dependencies import require_resource_grant
from rentivo.api.errors import ProblemException
from rentivo.api.principal import Principal
from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.organization import Organization, OrganizationMember
from rentivo.services.container import RequestServices


@dataclass(frozen=True, slots=True)
class BillingAccess:
    billing: Billing
    role: str
    principal: Principal


@dataclass(frozen=True, slots=True)
class BillAccess:
    bill: Bill
    billing: Billing
    role: str
    principal: Principal


@dataclass(frozen=True, slots=True)
class OrganizationAccess:
    organization: Organization
    member: OrganizationMember
    principal: Principal

    @property
    def role(self) -> str:
        return self.member.role


def resolve_billing_access(
    principal: Principal,
    services: RequestServices,
    billing_uuid: str,
) -> BillingAccess:
    billing = services.billing.get_billing_by_uuid(billing_uuid)
    if billing is None or billing.id is None:
        raise ProblemException.not_found()
    require_resource_grant(
        principal,
        services,
        billing.owner_type,
        billing.owner_id,
    )
    role = services.authorization.get_role_for_billing(principal.user.id, billing)
    if role is None:
        raise ProblemException.not_found()
    return BillingAccess(billing=billing, role=role, principal=principal)


def resolve_bill_access(
    principal: Principal,
    services: RequestServices,
    billing_uuid: str,
    bill_uuid: str,
) -> BillAccess:
    billing_access = resolve_billing_access(principal, services, billing_uuid)
    bill = services.bill.get_bill_by_uuid(bill_uuid)
    if bill is None or bill.id is None or bill.billing_id != billing_access.billing.id:
        raise ProblemException.not_found()
    return BillAccess(
        bill=bill,
        billing=billing_access.billing,
        role=billing_access.role,
        principal=principal,
    )


def resolve_organization_access(
    principal: Principal,
    services: RequestServices,
    organization_uuid: str,
) -> OrganizationAccess:
    organization = services.organization.get_by_uuid(organization_uuid)
    if organization is None or organization.id is None:
        raise ProblemException.not_found()
    require_resource_grant(
        principal,
        services,
        "organization",
        organization.id,
    )
    member = services.organization.get_member(organization.id, principal.user.id)
    if member is None:
        raise ProblemException.not_found()
    return OrganizationAccess(
        organization=organization,
        member=member,
        principal=principal,
    )


def require_role(role: str, allowed: Collection[str]) -> None:
    if role not in allowed:
        raise ProblemException.forbidden(
            "insufficient_role",
            "Você não possui permissão para esta operação.",
        )
