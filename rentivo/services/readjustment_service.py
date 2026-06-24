from __future__ import annotations

from datetime import date

import structlog

from rentivo.models.billing import Billing, ItemType, ReadjustmentIndex
from rentivo.observability import traced
from rentivo.services.bcb_sgs_client import IGPM_SERIES, IPCA_SERIES

logger = structlog.get_logger(__name__)

_SERIES_BY_INDEX = {
    ReadjustmentIndex.IGPM: IGPM_SERIES,
    ReadjustmentIndex.IPCA: IPCA_SERIES,
}


def series_for_index(index: ReadjustmentIndex) -> int | None:
    """SGS series code for an index, or None for NONE."""
    return _SERIES_BY_INDEX.get(index)


def readjust_amount(old_amount: int, pct: float) -> int:
    """Apply a percentage to a centavos amount with explicit rounding:
    ``new_amount = int(round(old_amount * (1 + pct / 100)))``."""
    return int(round(old_amount * (1 + pct / 100)))


class ReadjustmentService:
    def __init__(self, billing_service) -> None:
        self.billing_service = billing_service

    @traced("readjustment.preview")
    def preview(self, billing: Billing, pct: float) -> list[dict]:
        """Per-FIXED-item preview rows (no mutation, no persistence)."""
        return [
            {
                "id": item.id,
                "description": item.description,
                "old_amount": item.amount,
                "new_amount": readjust_amount(item.amount, pct),
            }
            for item in billing.items
            if item.item_type == ItemType.FIXED
        ]

    @traced("readjustment.apply")
    def apply(self, billing: Billing, pct: float, applied_on: date) -> Billing:
        """Readjust every FIXED item in-place, stamp last_readjustment_date,
        and persist via the injected BillingService."""
        for item in billing.items:
            if item.item_type == ItemType.FIXED:
                item.amount = readjust_amount(item.amount, pct)
        billing.last_readjustment_date = applied_on.isoformat()
        updated = self.billing_service.update_billing(billing)
        logger.info("billing_readjusted", billing_id=billing.id, pct=pct)
        return updated
