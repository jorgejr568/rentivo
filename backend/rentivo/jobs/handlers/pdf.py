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
    render_operation_id = payload.get("render_operation_id")
    if render_operation_id is not None and not isinstance(render_operation_id, str):
        raise PermanentJobError(f"pdf.render requires string render_operation_id, got {render_operation_id!r}")
    receipt_cleanup = payload.get("receipt_cleanup")
    if receipt_cleanup is not None:
        if (
            not isinstance(receipt_cleanup, dict)
            or not isinstance(receipt_cleanup.get("uuid"), str)
            or not isinstance(receipt_cleanup.get("storage_key"), str)
        ):
            raise PermanentJobError(f"pdf.render requires valid receipt_cleanup, got {receipt_cleanup!r}")
        if render_operation_id is None:
            raise PermanentJobError("pdf.render receipt_cleanup requires render_operation_id")

    engine = get_engine()
    with engine.connect() as conn:
        bill_repo = SQLAlchemyBillRepository(conn, get_encryption())
        billing_repo = SQLAlchemyBillingRepository(conn, get_encryption())
        receipt_repo = SQLAlchemyReceiptRepository(conn, get_encryption())
        bill = bill_repo.get_by_id(bill_id)
        storage = get_storage()
        if receipt_cleanup is not None:
            active_receipt = receipt_repo.get_by_uuid(receipt_cleanup["uuid"])
            if active_receipt is not None:
                current_operation_id = bill_repo.get_pdf_render_state(bill_id)[0] if bill is not None else None
                if current_operation_id == render_operation_id:
                    raise RuntimeError(f"receipt {receipt_cleanup['uuid']} is still active")
                logger.info(
                    "receipt_cleanup_cancelled",
                    bill_id=bill_id,
                    receipt_uuid=receipt_cleanup["uuid"],
                )
                return
            if receipt_cleanup["storage_key"]:
                storage.delete(receipt_cleanup["storage_key"])
                logger.info(
                    "receipt_cleanup_succeeded",
                    bill_id=bill_id,
                    receipt_uuid=receipt_cleanup["uuid"],
                )
        if bill is None:
            raise PermanentJobError(f"bill {bill_id} not found (deleted or never existed)")
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
            storage=storage,
            receipt_repo=receipt_repo,
            theme_service=theme,
            pix_service=pix,
            # No job_service — the handler is the queue consumer; nested enqueues
            # would be a bug. Forcing job_service=None makes _render_or_enqueue
            # fall through to the synchronous _render_pdf_sync path even if some
            # caller in BillService accidentally invokes the dispatcher.
        )

        legacy_payload = render_operation_id is None
        if legacy_payload:
            render_operation_id = payload.get("_job_ulid")
            if not isinstance(render_operation_id, str) or len(render_operation_id) != 26:
                raise PermanentJobError("legacy pdf.render requires persistent job identity")
            if not bill_repo.claim_pending_pdf_render(bill_id, render_operation_id):
                logger.info("pdf_render_legacy_claim_stale", bill_id=bill_id)
                return

        try:
            service._render_pdf_sync(
                bill,
                billing,
                render_operation_id=render_operation_id,
            )
        except ValueError as exc:
            if PIX_NOT_CONFIGURED_MESSAGE in str(exc):
                bill_repo.finish_pdf_render(bill_id, render_operation_id, "failed")
                raise PermanentJobError(str(exc)) from exc
            if legacy_payload:
                bill_repo.finish_pdf_render(bill_id, render_operation_id, "pending")
            raise
        except Exception:
            if legacy_payload:
                bill_repo.finish_pdf_render(bill_id, render_operation_id, "pending")
            raise

        logger.info("pdf_render_succeeded", bill_id=bill_id)


@register_on_fail("pdf.render")
def _on_pdf_render_failed(payload: dict) -> None:
    """Mark the affected bill 'failed' when the worker dead-letters the job."""
    bill_id = payload.get("bill_id")
    if not isinstance(bill_id, int):
        return
    render_operation_id = payload.get("render_operation_id")
    engine = get_engine()
    with engine.connect() as conn:
        bill_repo = SQLAlchemyBillRepository(conn, get_encryption())
        if isinstance(render_operation_id, str):
            bill_repo.finish_pdf_render(bill_id, render_operation_id, "failed")
        else:
            bill_repo.fail_pending_pdf_render_without_operation(bill_id)
        logger.warning("pdf_render_marked_failed", bill_id=bill_id)
