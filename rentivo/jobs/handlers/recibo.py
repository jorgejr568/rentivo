from __future__ import annotations

import structlog

from rentivo.db import get_engine
from rentivo.encryption.factory import get_encryption
from rentivo.jobs.base import PermanentJobError
from rentivo.jobs.registry import register
from rentivo.models.bill import BillStatus
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyThemeRepository,
    SQLAlchemyUserRepository,
)
from rentivo.services.bill_service import BillService
from rentivo.services.pix_service import PixService
from rentivo.services.theme_service import ThemeService
from rentivo.storage.factory import get_storage

logger = structlog.get_logger(__name__)


@register("recibo.render")
def handle_recibo_render(payload: dict) -> None:
    """Render and store a bill's payment-receipt (recibo) PDF in the background.

    Enqueued when a bill transitions to PAID. Payload shape: ``{"bill_id": int}``.

    Idempotency: the bill's status is re-checked here because it may have moved
    back out of PAID between the enqueue and this run — in which case the recibo
    must NOT be (re)created, or it would orphan a quittance for an unpaid bill.
    """
    bill_id = payload.get("bill_id")
    if not isinstance(bill_id, int):
        raise PermanentJobError(f"recibo.render requires int bill_id, got {bill_id!r}")

    engine = get_engine()
    with engine.connect() as conn:
        bill_repo = SQLAlchemyBillRepository(conn, get_encryption())
        billing_repo = SQLAlchemyBillingRepository(conn, get_encryption())
        bill = bill_repo.get_by_id(bill_id)
        if bill is None:
            raise PermanentJobError(f"bill {bill_id} not found (deleted or never existed)")
        if bill.status != BillStatus.PAID.value:
            logger.info("recibo_render_skipped_not_paid", bill_id=bill_id, status=bill.status)
            return
        billing = billing_repo.get_by_id(bill.billing_id)
        if billing is None:
            raise PermanentJobError(f"billing {bill.billing_id} not found for bill {bill_id}")

        pix = PixService(
            SQLAlchemyUserRepository(conn, get_encryption()),
            SQLAlchemyOrganizationRepository(conn, get_encryption()),
        )
        theme = ThemeService(SQLAlchemyThemeRepository(conn))
        service = BillService(
            bill_repo=bill_repo,
            storage=get_storage(),
            theme_service=theme,
            pix_service=pix,
            # No job_service — the handler is the queue consumer.
        )
        service.store_recibo(bill, billing)
        logger.info("recibo_render_succeeded", bill_id=bill_id)
