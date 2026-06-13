from __future__ import annotations

import structlog

from rentivo.communications.defaults import system_default_template
from rentivo.communications.render import month_long, substitute
from rentivo.models import format_brl
from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.communication import Communication, CommunicationTemplate
from rentivo.models.recipient import Recipient
from rentivo.repositories.base import CommunicationRepository, CommunicationTemplateRepository
from rentivo.services.job_service import JobService

logger = structlog.get_logger(__name__)


class CommunicationService:
    def __init__(
        self,
        communication_repo: CommunicationRepository,
        template_repo: CommunicationTemplateRepository,
        job_service: JobService,
    ) -> None:
        self.communication_repo = communication_repo
        self.template_repo = template_repo
        self.job_service = job_service

    # ---- templates ----

    def resolve_template(self, billing: Billing, comm_type: str) -> CommunicationTemplate:
        """Most-specific-wins: billing -> billing owner (user/org) -> system default."""
        billing_tmpl = self.template_repo.get("billing", billing.id, comm_type)
        if billing_tmpl is not None:
            return billing_tmpl
        owner_tmpl = self.template_repo.get(billing.owner_type, billing.owner_id, comm_type)
        if owner_tmpl is not None:
            return owner_tmpl
        return system_default_template(comm_type)

    def save_template(
        self, owner_type: str, owner_id: int, comm_type: str, subject: str, body_markdown: str
    ) -> CommunicationTemplate:
        return self.template_repo.upsert(
            CommunicationTemplate(
                owner_type=owner_type,
                owner_id=owner_id,
                comm_type=comm_type,
                subject=subject,
                body_markdown=body_markdown,
            )
        )

    # ---- sending ----

    @staticmethod
    def _context(bill: Bill, billing: Billing, recipient: Recipient) -> dict[str, str]:
        return {
            "nome_inquilino": recipient.name,
            "unidade": billing.name,
            "mes": month_long(bill.reference_month),
            "vencimento": bill.due_date or "",
            "total": format_brl(bill.total_amount),
        }

    def send(
        self,
        bill: Bill,
        billing: Billing,
        recipients: list[Recipient],
        subject_template: str,
        body_template: str,
        actor=None,
    ) -> list[Communication]:
        """Create one queued communication per recipient and enqueue a send job each."""
        results: list[Communication] = []
        # Per-recipient: create row, enqueue job, stamp job_ulid. Not atomic across
        # recipients — earlier recipients stay queued if a later one fails. If the
        # enqueue itself fails we mark that row 'failed' so it surfaces in the UI
        # instead of sitting 'queued' forever with no job to process it.
        for recipient in recipients:
            ctx = self._context(bill, billing, recipient)
            comm = self.communication_repo.create(
                Communication(
                    bill_id=bill.id,
                    comm_type="bill_ready",
                    recipient_name=recipient.name,
                    recipient_email=recipient.email,
                    subject=substitute(subject_template, ctx),
                    body_markdown=substitute(body_template, ctx),
                )
            )
            try:
                job = self.job_service.enqueue_for(
                    actor, "communication.send", {"communication_id": comm.id}, max_attempts=3
                )
            except Exception:
                self.communication_repo.mark_failed(comm.id, "Falha ao enfileirar o envio.")
                logger.exception("communication_enqueue_failed", communication_id=comm.id)
                raise
            self.communication_repo.set_job_ulid(comm.id, job.ulid)
            comm.job_ulid = job.ulid
            results.append(comm)
        logger.info("communications_enqueued", bill_id=bill.id, count=len(results))
        return results

    def list_for_bill(self, bill_id: int) -> list[Communication]:
        return self.communication_repo.list_by_bill(bill_id)
