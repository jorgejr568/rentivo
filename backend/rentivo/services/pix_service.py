from __future__ import annotations

from dataclasses import dataclass

import structlog

from rentivo.models.billing import Billing
from rentivo.observability import traced
from rentivo.repositories.base import OrganizationRepository, UserRepository

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PixConfig:
    pix_key: str
    merchant_name: str
    merchant_city: str


def _complete(pix_key: str, merchant_name: str, merchant_city: str) -> PixConfig | None:
    if pix_key and merchant_name and merchant_city:
        return PixConfig(pix_key=pix_key, merchant_name=merchant_name, merchant_city=merchant_city)
    return None


class PixService:
    """Resolves PIX configuration for billings, most-specific-wins.

    Resolution order (mirrors ThemeService pattern, billing override first):
    1. Billing override — if all three billing fields set
    2. Owner (user or organization, based on billing.owner_type) — if all three fields set
    3. None — caller must block invoice generation and prompt the user
    """

    def __init__(self, user_repo: UserRepository, org_repo: OrganizationRepository) -> None:
        self.user_repo = user_repo
        self.org_repo = org_repo
        # Request-scoped memo: a PixService is built per request, and a single
        # billing-list render resolves PIX for N billings that usually share one
        # owner (the logged-in user). Caching by (owner_type, owner_id) collapses
        # those N identical owner fetches into one query.
        self._owner_cache: dict[tuple[str, int], PixConfig | None] = {}

    @traced("pix.resolve_for_billing")
    def resolve_for_billing(self, billing: Billing) -> PixConfig | None:
        owner_cfg = self.get_owner_config(billing.owner_type, billing.owner_id)
        billing_cfg = _complete(billing.pix_key, billing.pix_merchant_name, billing.pix_merchant_city)
        # Billing-level override takes precedence when fully set, matching the
        # theme service pattern (most-specific wins).
        return billing_cfg or owner_cfg

    @traced("pix.get_owner_config")
    def get_owner_config(self, owner_type: str, owner_id: int) -> PixConfig | None:
        key = (owner_type, owner_id)
        if key not in self._owner_cache:
            self._owner_cache[key] = self._load_owner_config(owner_type, owner_id)
        return self._owner_cache[key]

    def _load_owner_config(self, owner_type: str, owner_id: int) -> PixConfig | None:
        if owner_type == "organization":
            org = self.org_repo.get_by_id(owner_id)
            if org is None:
                return None
            return _complete(org.pix_key, org.pix_merchant_name, org.pix_merchant_city)
        user = self.user_repo.get_by_id(owner_id)
        if user is None:
            return None
        return _complete(user.pix_key, user.pix_merchant_name, user.pix_merchant_city)

    @traced("pix.owner_needs_setup")
    def owner_needs_setup(self, owner_type: str, owner_id: int) -> bool:
        return self.get_owner_config(owner_type, owner_id) is None

    @traced("pix.billing_needs_setup")
    def billing_needs_setup(self, billing: Billing) -> bool:
        return self.resolve_for_billing(billing) is None
