from __future__ import annotations

from datetime import datetime
from email.utils import formataddr

import structlog

from rentivo.communications.render import render_markdown
from rentivo.constants import SP_TZ
from rentivo.db import get_engine
from rentivo.email.base import EmailAttachment
from rentivo.email.factory import get_email_backend
from rentivo.encryption.factory import get_encryption
from rentivo.jobs.base import PermanentJobError
from rentivo.jobs.registry import register, register_on_fail
from rentivo.models.communication import CommType
from rentivo.repositories.sqlalchemy.bill import SQLAlchemyBillRepository
from rentivo.repositories.sqlalchemy.billing import SQLAlchemyBillingRepository
from rentivo.repositories.sqlalchemy.communication import SQLAlchemyCommunicationRepository
from rentivo.repositories.sqlalchemy.organization import SQLAlchemyOrganizationRepository
from rentivo.repositories.sqlalchemy.reply_to import SQLAlchemyReplyToRecipientRepository
from rentivo.repositories.sqlalchemy.user import SQLAlchemyUserRepository
from rentivo.services.email_service import EmailService
from rentivo.settings import settings
from rentivo.storage.factory import get_storage

logger = structlog.get_logger(__name__)


def _require_int_id(payload: dict) -> int:
    communication_id = payload.get("communication_id")
    if not isinstance(communication_id, int):
        raise PermanentJobError(f"communication.send requires int communication_id, got {communication_id!r}")
    return communication_id


def _resolve_sender_name(conn, encryption, billing) -> str:
    """Human-facing sender name for the attribution block.

    Org-owned billing → organization name; user-owned → the account email.
    Resolved fresh at send time (like reply-to); never written to the plaintext
    job payload. Falls back to a generic label if a name can't be resolved.
    """
    name = ""
    if billing is not None:
        if billing.owner_type == "organization":
            org = SQLAlchemyOrganizationRepository(conn, encryption).get_by_id(billing.owner_id)
            if org is not None:
                name = org.name
        else:
            user = SQLAlchemyUserRepository(conn, encryption).get_by_id(billing.owner_id)
            if user is not None:
                name = user.email
    return name or "o responsável"


@register("communication.send")
def handle_communication_send(payload: dict) -> None:
    """Render a stored communication, attach the bill PDF, send one email, mark sent.

    Payload shape: ``{"communication_id": int}``.
    """
    communication_id = _require_int_id(payload)
    engine = get_engine()
    encryption = get_encryption()
    with engine.connect() as conn:
        comm_repo = SQLAlchemyCommunicationRepository(conn, encryption)
        comm = comm_repo.get_by_id(communication_id)
        if comm is None:
            raise PermanentJobError(f"communication {communication_id} not found")

        # Idempotency: the job framework is at-least-once (a crash after the email
        # is sent but before mark_sent leaves the job to be retried). Only a still-
        # queued row should be sent, so a retry of an already-delivered one is a
        # no-op instead of a duplicate invoice email to the tenant.
        if comm.status != "queued":
            logger.info("communication_send_skipped", communication_id=comm.id, status=comm.status)
            return

        bill = SQLAlchemyBillRepository(conn, encryption).get_by_id(comm.bill_id)
        if bill is None:
            raise PermanentJobError(f"bill {comm.bill_id} missing")

        # The attached document depends on the communication type: a recibo
        # (payment-receipt) send carries the stored recibo PDF; everything else
        # carries the invoice PDF.
        if comm.comm_type == CommType.PAYMENT_RECEIPT.value:
            attachment_key = bill.recibo_pdf_path
            attachment_filename = f"recibo-{bill.reference_month}.pdf"
            doc_label = "recibo"
        else:
            attachment_key = bill.pdf_path
            attachment_filename = f"fatura-{bill.reference_month}.pdf"
            doc_label = "invoice"
        if not attachment_key:
            raise PermanentJobError(f"bill {comm.bill_id} has no {doc_label} PDF")

        try:
            pdf_bytes = get_storage().get(attachment_key)
        except FileNotFoundError as exc:
            # The DB still references a key whose object is gone — it will never
            # reappear, so fail permanently instead of burning every retry.
            raise PermanentJobError(f"bill {comm.bill_id} {doc_label} object missing at {attachment_key!r}") from exc

        # Reply-To is delivery config, resolved fresh from the billing at send time
        # (unlike subject/body, which are snapshotted onto the communication row).
        reply_to_contacts = SQLAlchemyReplyToRecipientRepository(conn, encryption).list_by_billing(bill.billing_id)
        reply_to = [formataddr((r.name, r.email)) for r in reply_to_contacts]

        billing = SQLAlchemyBillingRepository(conn, encryption).get_by_id(bill.billing_id)
        sender_name = _resolve_sender_name(conn, encryption, billing)

        # From email and name fall back to their SES-level defaults INDEPENDENTLY:
        # setting only communications_from_email (no name) pairs that email with
        # ses_from_name, and vice-versa. Intended — configure only what differs.
        from_email = settings.communications_from_email or settings.ses_from_email or "noreply@localhost"
        from_name = settings.communications_from_name or settings.ses_from_name
        from_address = formataddr((from_name, from_email))
        service = EmailService(get_email_backend(), from_address=from_address)
        body_html = render_markdown(comm.body_markdown)
        attachment = EmailAttachment(
            filename=attachment_filename,
            content=pdf_bytes,
            content_type="application/pdf",
        )
        service.send_communication(
            comm.recipient_email,
            comm.subject,
            body_html,
            comm.body_markdown,
            [attachment],
            reply_to=reply_to,
            sender_name=sender_name,
            # Unique X-Entity-Ref-ID per communication so Gmail does not thread them.
            headers=(("X-Entity-Ref-ID", comm.uuid),),
        )
        comm_repo.mark_sent(comm.id, datetime.now(SP_TZ))
        logger.info("communication_sent", communication_id=comm.id, bill_id=bill.id)


@register_on_fail("communication.send")
def _on_communication_send_failed(payload: dict) -> None:
    """Dead-letter hook: mark the communication failed so the UI can show it."""
    communication_id = payload.get("communication_id")
    if not isinstance(communication_id, int):  # pragma: no cover - guarded upstream
        return
    engine = get_engine()
    with engine.connect() as conn:
        repo = SQLAlchemyCommunicationRepository(conn, get_encryption())
        comm = repo.get_by_id(communication_id)
        # If a prior attempt actually delivered the email (status already 'sent'),
        # don't flip it back to 'failed' — that would mislead the operator into
        # resending and double-mailing the tenant.
        if comm is not None and comm.status == "sent":
            logger.info("communication_fail_hook_skipped_sent", communication_id=communication_id)
            return
        repo.mark_failed(communication_id, "Falha no envio após múltiplas tentativas.")
