"""Route-layer receipt attachment helper.

Lives in web/ (not rentivo/services/) because it consumes Starlette
``UploadFile`` objects and flashes PT-BR messages — both web concerns.
Unifies the previously duplicated upload-read -> validate -> add_receipt ->
audit loop from bill_generate and receipt_upload, resolving their divergence
toward the informative behavior: invalid files are counted and a warning is
flashed (bill_generate used to drop them silently).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from fastapi import Request
from starlette.datastructures import UploadFile

from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.receipt import ALLOWED_RECEIPT_TYPES, MAX_RECEIPT_SIZE
from rentivo.services.audit_serializers import serialize_receipt
from web.flash import flash

logger = structlog.get_logger(__name__)

SKIPPED_RECEIPTS_WARNING = "{count} arquivo(s) ignorado(s) (tipo inválido, vazio ou muito grande)."


@dataclass(frozen=True, slots=True)
class AttachResult:
    attached: int = 0
    skipped: int = 0
    total_bytes: int = 0


async def attach_receipts(
    request: Request, bill: Bill, billing: Billing, uploads: list, *, render: bool = True
) -> AttachResult:
    """Validate uploads, attach the valid ones to ``bill``, audit each one.

    Entries that are not ``UploadFile`` instances or have no filename are
    ignored (browsers send empty parts for unselected file inputs). Files with
    a disallowed content type, empty body, or body over ``MAX_RECEIPT_SIZE``
    count as skipped; when any are skipped a PT-BR warning is flashed.

    Files are always attached without rendering per file; with ``render=True``
    (the default, used by the standalone upload endpoint) the PDF is rendered
    exactly ONCE after every file is attached — uploading N receipts enqueues a
    single ``pdf.render`` job, not N racing ones. ``render=False`` skips the
    final render too, so the bill-create flow can render once itself afterwards.
    """
    bill_service = request.state.services.bill
    audit = request.state.services.audit
    attached = 0
    skipped = 0
    total_bytes = 0

    for upload in uploads:
        if not isinstance(upload, UploadFile) or not upload.filename:
            continue
        file_bytes = await upload.read()
        content_type = upload.content_type or ""
        if content_type not in ALLOWED_RECEIPT_TYPES or not file_bytes or len(file_bytes) > MAX_RECEIPT_SIZE:
            logger.warning(
                "receipt_upload_skipped",
                bill_uuid=bill.uuid,
                content_type=content_type,
                size=len(file_bytes),
            )
            skipped += 1
            continue

        # Never render per file — render once after the loop (see below).
        receipt, _ = bill_service.add_receipt(
            bill=bill,
            billing=billing,
            filename=upload.filename,
            file_bytes=file_bytes,
            content_type=content_type,
            actor=request.state.actor,
            render=False,
        )
        attached += 1
        total_bytes += len(file_bytes)

        audit.safe_log_for(
            request.state.actor,
            AuditEventType.RECEIPT_UPLOAD,
            entity_type="receipt",
            entity_id=receipt.id,
            entity_uuid=receipt.uuid,
            new_state=serialize_receipt(receipt, bill_uuid=bill.uuid, billing_uuid=billing.uuid),
        )

    # One render for the whole batch, only when the caller asked for it.
    if render and attached:
        bill_service.regenerate_pdf(bill, billing, actor=request.state.actor)

    if skipped:
        flash(request, SKIPPED_RECEIPTS_WARNING.format(count=skipped), "warning")
    return AttachResult(attached=attached, skipped=skipped, total_bytes=total_bytes)
