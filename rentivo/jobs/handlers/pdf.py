from __future__ import annotations

import structlog

from rentivo.db import get_engine
from rentivo.encryption.factory import get_encryption
from rentivo.jobs.base import PermanentJobError
from rentivo.jobs.registry import register, register_on_fail
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyReceiptRepository,
    SQLAlchemyThemeRepository,
    SQLAlchemyUserRepository,
)
from rentivo.services.bill_service import PIX_NOT_CONFIGURED_MESSAGE, BillService
from rentivo.services.pix_service import PixService
from rentivo.services.theme_service import ThemeService
from rentivo.storage.factory import get_storage

logger = structlog.get_logger(__name__)


@register("pdf.render")
def handle_pdf_render(payload: dict) -> None:
    """Render a bill's PDF in the background.

    Payload shape: ``{"bill_id": int}``.
    """
    bill_id = payload.get("bill_id")
    if not isinstance(bill_id, int):
        raise PermanentJobError(f"pdf.render requires int bill_id, got {bill_id!r}")

    engine = get_engine()
    with engine.connect() as conn:
        bill_repo = SQLAlchemyBillRepository(conn)
        billing_repo = SQLAlchemyBillingRepository(conn, get_encryption())
        bill = bill_repo.get_by_id(bill_id)
        if bill is None:
            raise PermanentJobError(f"bill {bill_id} not found (deleted or never existed)")
        billing = billing_repo.get_by_id(bill.billing_id)
        if billing is None:
            raise PermanentJobError(f"billing {bill.billing_id} not found for bill {bill_id}")

        pix = PixService(SQLAlchemyUserRepository(conn, get_encryption()), SQLAlchemyOrganizationRepository(conn))
        theme = ThemeService(SQLAlchemyThemeRepository(conn))
        service = BillService(
            bill_repo=bill_repo,
            storage=get_storage(),
            receipt_repo=SQLAlchemyReceiptRepository(conn),
            theme_service=theme,
            pix_service=pix,
            # No job_service — the handler is the queue consumer; nested enqueues
            # would be a bug. Forcing job_service=None makes _render_or_enqueue
            # fall through to the synchronous _render_pdf_sync path even if some
            # caller in BillService accidentally invokes the dispatcher.
        )

        try:
            service._render_pdf_sync(bill, billing)
        except ValueError as exc:
            if PIX_NOT_CONFIGURED_MESSAGE in str(exc):
                bill_repo.update_pdf_render_status(bill_id, "failed")
                raise PermanentJobError(str(exc)) from exc
            raise

        # _render_pdf_sync sets status='succeeded'; the explicit call here is
        # a guard against future refactors of that method.
        bill_repo.update_pdf_render_status(bill_id, "succeeded")
        logger.info("pdf_render_succeeded", bill_id=bill_id)


@register_on_fail("pdf.render")
def _on_pdf_render_failed(payload: dict) -> None:
    """Mark the affected bill 'failed' when the worker dead-letters the job."""
    bill_id = payload.get("bill_id")
    if not isinstance(bill_id, int):
        return
    engine = get_engine()
    with engine.connect() as conn:
        SQLAlchemyBillRepository(conn).update_pdf_render_status(bill_id, "failed")
        logger.warning("pdf_render_marked_failed", bill_id=bill_id)
