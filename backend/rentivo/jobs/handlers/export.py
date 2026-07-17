from __future__ import annotations

from email.utils import formataddr
from uuid import uuid4

import structlog

from rentivo.db import get_engine
from rentivo.email.base import EmailAttachment
from rentivo.email.factory import get_email_backend
from rentivo.encryption.factory import get_encryption
from rentivo.export.serializers import export_filename, format_label, serialize_rows
from rentivo.jobs.base import PermanentJobError
from rentivo.jobs.factory import get_job_backend
from rentivo.jobs.registry import register
from rentivo.repositories.sqlalchemy.audit_log import SQLAlchemyAuditLogRepository
from rentivo.repositories.sqlalchemy.bill import SQLAlchemyBillRepository
from rentivo.repositories.sqlalchemy.billing import SQLAlchemyBillingRepository
from rentivo.repositories.sqlalchemy.user import SQLAlchemyUserRepository
from rentivo.services.audit_service import AuditService
from rentivo.services.email_service import EmailService
from rentivo.services.export_service import ExportService
from rentivo.services.job_service import JobService
from rentivo.settings import settings
from rentivo.storage.factory import get_storage

logger = structlog.get_logger(__name__)


def _bare(content_type: str) -> str:
    """Strip any charset param so the value is a clean MIME type for storage
    and for the email attachment part built later in export.send."""
    return content_type.split(";")[0]


def _require_int(payload: dict, key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise PermanentJobError(f"export job requires int {key}, got {value!r}")
    return value


@register("export.generate")
def handle_export_generate(payload: dict) -> None:
    """Build a billing's bill export, upload it to storage, and enqueue export.send.

    Payload: ``{"billing_id": int, "format": "csv"|"xlsx", "requested_by_user_id": int}``.

    The file is built off the request path, written to storage under
    ``{billing_uuid}/exports/{token}.{ext}``, and an ``export.send`` job is
    enqueued to mail it to the requesting account and then clean up the object.
    Recipients (tenants) are NOT involved — the export is for the requester.

    At-least-once: a crash after upload but before the enqueue commits leaves an
    orphan object (a new run uses a fresh token). Orphans are harmless temp
    files; the eventual successful run's ``export.send`` deletes its own object.
    """
    billing_id = _require_int(payload, "billing_id")
    requested_by_user_id = _require_int(payload, "requested_by_user_id")
    fmt = payload.get("format", "csv")

    engine = get_engine()
    encryption = get_encryption()
    with engine.connect() as conn:
        billing = SQLAlchemyBillingRepository(conn, encryption).get_by_id(billing_id)
        if billing is None:
            raise PermanentJobError(f"billing {billing_id} not found")
        bills = SQLAlchemyBillRepository(conn, encryption).list_by_billing(billing_id)

        rows = ExportService().build_rows(billing, bills)
        body, content_type, ext = serialize_rows(fmt, ExportService.HEADERS, rows)

        storage_key = f"{billing.uuid}/exports/{uuid4().hex}.{ext}"
        get_storage().save(storage_key, body, content_type=_bare(content_type))

        job_service = JobService(
            get_job_backend(conn),
            AuditService(SQLAlchemyAuditLogRepository(conn)),
        )
        job_service.enqueue(
            "export.send",
            {
                "storage_key": storage_key,
                "content_type": _bare(content_type),
                "format": ext,
                "bill_count": len(bills),
                "billing_id": billing_id,
                "requested_by_user_id": requested_by_user_id,
            },
            source="worker",
        )

    logger.info(
        "export_generated",
        billing_id=billing_id,
        storage_key=storage_key,
        bill_count=len(bills),
        export_format=ext,
    )


@register("export.send")
def handle_export_send(payload: dict) -> None:
    """E-mail a previously-built export to the requesting account, then clean up.

    Payload: ``{"storage_key", "content_type", "format", "bill_count",
    "billing_id", "requested_by_user_id"}``.

    The requester's e-mail is resolved fresh from the encrypted ``users`` row
    (so no plaintext PII rides in the job payload). The file is pulled from
    storage, mailed as a single attachment to that account — never to the
    billing's tenant recipients — and an ``s3.delete`` job is enqueued to remove
    the temp object. At-least-once: a retry re-downloads and re-sends (a
    duplicate accounting export is benign) and re-enqueues the delete.
    """
    billing_id = _require_int(payload, "billing_id")
    user_id = _require_int(payload, "requested_by_user_id")
    storage_key = payload["storage_key"]
    content_type = payload["content_type"]
    ext = payload.get("format", "csv")
    bill_count = payload.get("bill_count", 0)

    engine = get_engine()
    encryption = get_encryption()
    with engine.connect() as conn:
        user = SQLAlchemyUserRepository(conn, encryption).get_by_id(user_id)
        if user is None:
            raise PermanentJobError(f"requesting user {user_id} not found")
        billing = SQLAlchemyBillingRepository(conn, encryption).get_by_id(billing_id)
        if billing is None:
            raise PermanentJobError(f"billing {billing_id} not found")

    # If the object is missing we let the error propagate as a transient retry.
    # The common cause is a not-yet-consistent read right after export.generate's
    # upload; a genuinely-gone object (e.g. a duplicate run after s3.delete
    # already fired) simply exhausts retries and dead-letters — the email for
    # that export was already sent on the first, successful run.
    data = get_storage().get(storage_key)
    attachment = EmailAttachment(
        filename=export_filename(billing.name, ext),
        content=data,
        content_type=content_type,
    )

    from_address = formataddr((settings.ses_from_name, settings.ses_from_email or "noreply@localhost"))
    service = EmailService(get_email_backend(), from_address=from_address)
    service.send(
        user.email,
        "export_ready",
        {
            "recipient_name": "",
            "billing_name": billing.name,
            "bill_count": bill_count,
            "format_label": format_label(ext),
        },
        attachments=[attachment],
    )

    with engine.connect() as conn:
        job_service = JobService(
            get_job_backend(conn),
            AuditService(SQLAlchemyAuditLogRepository(conn)),
        )
        job_service.enqueue("s3.delete", {"key": storage_key}, source="worker")

    logger.info(
        "export_sent",
        billing_id=billing_id,
        user_id=user_id,
        storage_key=storage_key,
        bill_count=bill_count,
        export_format=ext,
    )
