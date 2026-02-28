from __future__ import annotations

import logging

from rentivo.models.billing import Billing, BillingItem
from rentivo.repositories.base import BillingRepository

logger = logging.getLogger(__name__)


class BillingService:
    def __init__(self, repo: BillingRepository) -> None:
        self.repo = repo

    def create_billing(
        self,
        name: str,
        description: str,
        items: list[BillingItem],
        pix_key: str = "",
        owner_type: str = "user",
        owner_id: int = 0,
    ) -> Billing:
        billing = Billing(
            name=name,
            description=description,
            items=items,
            pix_key=pix_key,
            owner_type=owner_type,
            owner_id=owner_id,
        )
        result = self.repo.create(billing)
        logger.info("Billing created: id=%s, name=%s", result.id, result.name)
        return result

    def list_billings(self) -> list[Billing]:
        result = self.repo.list_all()
        logger.debug("Listed %d billings (all)", len(result))
        return result

    def list_billings_for_user(self, user_id: int) -> list[Billing]:
        result = self.repo.list_for_user(user_id)
        logger.debug("Listed %d billings for user=%s", len(result), user_id)
        return result

    def get_billing(self, billing_id: int) -> Billing | None:
        result = self.repo.get_by_id(billing_id)
        logger.debug("get_billing id=%s found=%s", billing_id, result is not None)
        return result

    def get_billing_by_uuid(self, uuid: str) -> Billing | None:
        result = self.repo.get_by_uuid(uuid)
        logger.debug("get_billing_by_uuid uuid=%s found=%s", uuid, result is not None)
        return result

    def update_billing(self, billing: Billing) -> Billing:
        result = self.repo.update(billing)
        logger.info("Billing updated: id=%s, name=%s", result.id, result.name)
        return result

    def delete_billing(self, billing_id: int) -> None:
        self.repo.delete(billing_id)
        logger.info("Billing %s soft-deleted", billing_id)

    def transfer_to_organization(self, billing_id: int, org_id: int) -> None:
        billing = self.repo.get_by_id(billing_id)
        if billing is None:
            logger.warning("Transfer failed: billing %s not found", billing_id)
            raise ValueError("Billing not found")
        if billing.owner_type != "user":
            logger.warning("Transfer failed: billing %s is not user-owned", billing_id)
            raise ValueError("Only personal billings can be transferred to organizations")
        self.repo.transfer_owner(billing_id, "organization", org_id)
        logger.info("Billing %s transferred to organization %s", billing_id, org_id)
