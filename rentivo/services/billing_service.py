from __future__ import annotations

import structlog

from rentivo.models.billing import Billing, BillingItem
from rentivo.pix import validate_pix_key
from rentivo.repositories.base import BillingRepository

logger = structlog.get_logger(__name__)


def _normalize_pix_key(value: str) -> str:
    """Return a normalized PIX key, or '' if the value is empty. Raises ValueError if invalid."""
    if not value or not value.strip():
        return ""
    return validate_pix_key(value)


class BillingService:
    def __init__(self, repo: BillingRepository) -> None:
        self.repo = repo

    def create_billing(
        self,
        name: str,
        description: str,
        items: list[BillingItem],
        pix_key: str = "",
        pix_merchant_name: str = "",
        pix_merchant_city: str = "",
        owner_type: str = "user",
        owner_id: int = 0,
    ) -> Billing:
        billing = Billing(
            name=name,
            description=description,
            items=items,
            pix_key=_normalize_pix_key(pix_key),
            pix_merchant_name=pix_merchant_name.strip(),
            pix_merchant_city=pix_merchant_city.strip(),
            owner_type=owner_type,
            owner_id=owner_id,
        )
        result = self.repo.create(billing)
        logger.info("billing_created", billing_id=result.id, name=result.name)
        return result

    def list_billings(self) -> list[Billing]:
        result = self.repo.list_all()
        logger.debug("billings_listed_all", count=len(result))
        return result

    def list_billings_for_user(self, user_id: int) -> list[Billing]:
        result = self.repo.list_for_user(user_id)
        logger.debug("billings_listed_for_user", count=len(result), user_id=user_id)
        return result

    def get_billing(self, billing_id: int) -> Billing | None:
        result = self.repo.get_by_id(billing_id)
        logger.debug("billing_get", billing_id=billing_id, found=result is not None)
        return result

    def get_billing_by_uuid(self, uuid: str) -> Billing | None:
        result = self.repo.get_by_uuid(uuid)
        logger.debug("billing_get_by_uuid", billing_uuid=uuid, found=result is not None)
        return result

    def update_billing(self, billing: Billing) -> Billing:
        billing.pix_key = _normalize_pix_key(billing.pix_key)
        billing.pix_merchant_name = billing.pix_merchant_name.strip()
        billing.pix_merchant_city = billing.pix_merchant_city.strip()
        result = self.repo.update(billing)
        logger.info("billing_updated", billing_id=result.id, name=result.name)
        return result

    def delete_billing(self, billing_id: int) -> None:
        self.repo.delete(billing_id)
        logger.info("billing_deleted", billing_id=billing_id)

    def transfer_to_organization(self, billing_id: int, org_id: int) -> None:
        billing = self.repo.get_by_id(billing_id)
        if billing is None:
            logger.warning("billing_transfer_failed", billing_id=billing_id, reason="not_found")
            raise ValueError("Billing not found")
        if billing.owner_type != "user":
            logger.warning(
                "billing_transfer_failed",
                billing_id=billing_id,
                reason="not_user_owned",
                owner_type=billing.owner_type,
            )
            raise ValueError("Only personal billings can be transferred to organizations")
        self.repo.transfer_owner(billing_id, "organization", org_id)
        logger.info("billing_transferred", billing_id=billing_id, org_id=org_id)
