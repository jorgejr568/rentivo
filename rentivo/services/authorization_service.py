from __future__ import annotations

import logging

from rentivo.models.billing import Billing
from rentivo.repositories.base import OrganizationRepository

logger = logging.getLogger(__name__)


class AuthorizationService:
    def __init__(self, org_repo: OrganizationRepository | None = None) -> None:
        self.org_repo = org_repo

    def get_role_for_billing(self, user_id: int, billing: Billing) -> str | None:
        if billing.owner_type == "user" and billing.owner_id == user_id:
            logger.debug("user=%s billing=%s role=owner", user_id, billing.id)
            return "owner"
        if billing.owner_type == "organization" and self.org_repo is not None:
            member = self.org_repo.get_member(billing.owner_id, user_id)
            if member is not None:
                logger.debug("user=%s billing=%s role=%s", user_id, billing.id, member.role)
                return member.role
        logger.debug("user=%s billing=%s role=None", user_id, billing.id)
        return None

    def can_view_billing(self, user_id: int, billing: Billing) -> bool:
        result = self.get_role_for_billing(user_id, billing) is not None
        logger.debug("user=%s billing=%s can_view=%s", user_id, billing.id, result)
        return result

    def can_edit_billing(self, user_id: int, billing: Billing) -> bool:
        role = self.get_role_for_billing(user_id, billing)
        result = role in ("owner", "admin")
        logger.debug("user=%s billing=%s can_edit=%s", user_id, billing.id, result)
        return result

    def can_delete_billing(self, user_id: int, billing: Billing) -> bool:
        result = self.can_edit_billing(user_id, billing)
        logger.debug("user=%s billing=%s can_delete=%s", user_id, billing.id, result)
        return result

    def can_manage_bills(self, user_id: int, billing: Billing) -> bool:
        role = self.get_role_for_billing(user_id, billing)
        result = role in ("owner", "admin", "manager")
        logger.debug("user=%s billing=%s can_manage_bills=%s", user_id, billing.id, result)
        return result

    def can_transfer_billing(self, user_id: int, billing: Billing) -> bool:
        result = billing.owner_type == "user" and billing.owner_id == user_id
        logger.debug("user=%s billing=%s can_transfer=%s", user_id, billing.id, result)
        return result
