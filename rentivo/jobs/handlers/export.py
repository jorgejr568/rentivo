from __future__ import annotations

from email.utils import formataddr

import structlog

from rentivo.db import get_engine
from rentivo.email.base import EmailAttachment
from rentivo.email.factory import get_email_backend
from rentivo.encryption.factory import get_encryption
from rentivo.export.serializers import export_filename, serialize_rows
from rentivo.jobs.base import PermanentJobError
from rentivo.jobs.registry import register
from rentivo.repositories.sqlalchemy.bill import SQLAlchemyBillRepository
from rentivo.repositories.sqlalchemy.billing import SQLAlchemyBillingRepository
from rentivo.repositories.sqlalchemy.recipient import SQLAlchemyRecipientRepository
from rentivo.services.email_service import EmailService
from rentivo.services.export_service import ExportService
from rentivo.settings import settings

logger = structlog.get_logger(__name__)


def _require_int(payload: dict, key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise PermanentJobError(f"export.generate requires int {key}, got {value!r}")
    return value


@register("export.generate")
def handle_export_generate(payload: dict) -> None:
    """Build a billing's bill export and email it to the billing's recipients.

    Payload shape: ``{"billing_id": int, "format": "csv" | "xlsx"}``.

    The file is generated in the worker (off the request path) and attached to
    one email per recipient — never CC'd. Recipient name/email are resolved
    fresh from the encrypted ``billing_recipients`` rows, so no PII rides in the
    plaintext job payload. The job is at-least-once: a crash mid-batch retries
    the whole send, which may re-deliver the export to already-mailed
    recipients. A duplicate accounting export is benign, so we accept that
    rather than tracking per-recipient delivery state.
    """
    billing_id = _require_int(payload, "billing_id")
    fmt = payload.get("format", "csv")
    engine = get_engine()
    encryption = get_encryption()
    with engine.connect() as conn:
        billing = SQLAlchemyBillingRepository(conn, encryption).get_by_id(billing_id)
        if billing is None:
            raise PermanentJobError(f"billing {billing_id} not found")
        recipients = SQLAlchemyRecipientRepository(conn, encryption).list_by_billing(billing_id)
        if not recipients:
            # The route guards against this, but a recipient could be removed
            # between enqueue and run. Nothing to send — succeed without retry.
            logger.info("export_skipped_no_recipients", billing_id=billing_id)
            return
        bills = SQLAlchemyBillRepository(conn, encryption).list_by_billing(billing_id)

    rows = ExportService().build_rows(billing, bills)
    body, content_type, ext = serialize_rows(fmt, ExportService.HEADERS, rows)
    attachment = EmailAttachment(
        filename=export_filename(billing.name, ext),
        content=body,
        # The MIME attachment part wants a bare content type (no charset param).
        content_type=content_type.split(";")[0],
    )

    from_address = formataddr((settings.ses_from_name, settings.ses_from_email or "noreply@localhost"))
    service = EmailService(get_email_backend(), from_address=from_address)
    for recipient in recipients:
        service.send(
            recipient.email,
            "export_ready",
            {
                "recipient_name": recipient.name,
                "billing_name": billing.name,
                "bill_count": len(bills),
                "format_label": ext.upper(),
            },
            attachments=[attachment],
        )
    logger.info(
        "export_sent",
        billing_id=billing_id,
        recipient_count=len(recipients),
        bill_count=len(bills),
        export_format=ext,
    )
