from __future__ import annotations

from datetime import datetime

import structlog

from rentivo.communications.render import render_markdown
from rentivo.constants import SP_TZ
from rentivo.db import get_engine
from rentivo.email.base import EmailAttachment
from rentivo.email.factory import get_email_backend
from rentivo.encryption.factory import get_encryption
from rentivo.jobs.base import PermanentJobError
from rentivo.jobs.registry import register, register_on_fail
from rentivo.repositories.sqlalchemy.bill import SQLAlchemyBillRepository
from rentivo.repositories.sqlalchemy.communication import SQLAlchemyCommunicationRepository
from rentivo.services.email_service import EmailService
from rentivo.settings import settings
from rentivo.storage.factory import get_storage

logger = structlog.get_logger(__name__)


def _require_int_id(payload: dict) -> int:
    communication_id = payload.get("communication_id")
    if not isinstance(communication_id, int):
        raise PermanentJobError(f"communication.send requires int communication_id, got {communication_id!r}")
    return communication_id


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

        bill = SQLAlchemyBillRepository(conn, encryption).get_by_id(comm.bill_id)
        if bill is None or not bill.pdf_path:
            raise PermanentJobError(f"bill {comm.bill_id} missing or has no PDF")

        pdf_bytes = get_storage().get(bill.pdf_path)

        service = EmailService(get_email_backend(), from_address=settings.ses_from_email or "noreply@localhost")
        body_html = render_markdown(comm.body_markdown)
        attachment = EmailAttachment(
            filename=f"fatura-{bill.reference_month}.pdf",
            content=pdf_bytes,
            content_type="application/pdf",
        )
        service.send_communication(comm.recipient_email, comm.subject, body_html, comm.body_markdown, [attachment])
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
        repo.mark_failed(communication_id, "Falha no envio após múltiplas tentativas.")
