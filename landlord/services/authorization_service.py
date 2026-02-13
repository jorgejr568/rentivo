from __future__ import annotations

import logging

from landlord.models.billing import Billing
from landlord.repositories.base import OrganizationRepository

logger = logging.getLogger(__name__)


class AuthorizationService:
    def __init__(self, org_repo: OrganizationRepository | None = None) -> None:
        self.org_repo = org_repo

    def get_role_for_billing(self, user_id: int, billing: Billing) -> str | None:
        if billing.owner_type == "user" and billing.owner_id == user_id:
            return "owner"
        if billing.owner_type == "organization" and self.org_repo is not None:
            member = self.org_repo.get_member(billing.owner_id, user_id)
            if member is not None:
                return member.role
        return None

    def can_view_billing(self, user_id: int, billing: Billing) -> bool:
        return self.get_role_for_billing(user_id, billing) is not None

    def can_edit_billing(self, user_id: int, billing: Billing) -> bool:
        role = self.get_role_for_billing(user_id, billing)
        return role in ("owner", "admin")

    def can_delete_billing(self, user_id: int, billing: Billing) -> bool:
        return self.can_edit_billing(user_id, billing)

    def can_manage_bills(self, user_id: int, billing: Billing) -> bool:
        role = self.get_role_for_billing(user_id, billing)
        return role in ("owner", "admin", "manager")

    def can_transfer_billing(self, user_id: int, billing: Billing) -> bool:
        return billing.owner_type == "user" and billing.owner_id == user_id
