from __future__ import annotations

import structlog

from rentivo.models.billing import Billing
from rentivo.repositories.base import OrganizationRepository

logger = structlog.get_logger(__name__)


class AuthorizationService:
    def __init__(self, org_repo: OrganizationRepository | None = None) -> None:
        self.org_repo = org_repo

    def get_role_for_billing(self, user_id: int, billing: Billing) -> str | None:
        if billing.owner_type == "user" and billing.owner_id == user_id:
            logger.debug("authz_role", user_id=user_id, billing_id=billing.id, role="owner")
            return "owner"
        if billing.owner_type == "organization" and self.org_repo is not None:
            member = self.org_repo.get_member(billing.owner_id, user_id)
            if member is not None:
                logger.debug("authz_role", user_id=user_id, billing_id=billing.id, role=member.role)
                return member.role
        logger.debug("authz_role", user_id=user_id, billing_id=billing.id, role=None)
        return None

    def can_view_billing(self, user_id: int, billing: Billing) -> bool:
        result = self.get_role_for_billing(user_id, billing) is not None
        logger.debug("authz_check", user_id=user_id, billing_id=billing.id, action="view", allowed=result)
        return result

    def can_edit_billing(self, user_id: int, billing: Billing) -> bool:
        role = self.get_role_for_billing(user_id, billing)
        result = role in ("owner", "admin")
        logger.debug("authz_check", user_id=user_id, billing_id=billing.id, action="edit", allowed=result)
        return result

    def can_delete_billing(self, user_id: int, billing: Billing) -> bool:
        result = self.can_edit_billing(user_id, billing)
        logger.debug("authz_check", user_id=user_id, billing_id=billing.id, action="delete", allowed=result)
        return result

    def can_manage_bills(self, user_id: int, billing: Billing) -> bool:
        role = self.get_role_for_billing(user_id, billing)
        result = role in ("owner", "admin", "manager")
        logger.debug("authz_check", user_id=user_id, billing_id=billing.id, action="manage_bills", allowed=result)
        return result

    def can_transfer_billing(self, user_id: int, billing: Billing) -> bool:
        result = billing.owner_type == "user" and billing.owner_id == user_id
        logger.debug("authz_check", user_id=user_id, billing_id=billing.id, action="transfer", allowed=result)
        return result
