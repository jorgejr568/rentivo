"""Automated payment reminders / dunning (REN-6).

Scans issued-but-unpaid bills and, for each configured offset relative to the
due date (D-3, due date, D+3 by default), sends one reminder per recipient —
once. The send-step is delegated to a ``ReminderChannel`` (email today) so the
*decision* logic here is channel-agnostic.

Idempotency: each (bill, offset) reminder is recorded as a Communication row
with an offset-specific ``comm_type``. Before sending, the service checks for an
existing queued/sent row for that bill+offset and skips it, so re-running the
sweep on the same day never double-mails a tenant. A previously *failed*
reminder is allowed to retry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import structlog

from rentivo.communications.channels import ReminderChannel
from rentivo.communications.reminders import (
    REMINDABLE_BILL_STATUSES,
    REMINDER_TEMPLATE_COMM_TYPE,
    days_until_due,
    offset_comm_type,
)
from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.observability import traced
from rentivo.services.communication_service import CommunicationService

logger = structlog.get_logger(__name__)

# Communication statuses that count as "already reminded" for dedup. A 'failed'
# row does not, so a delivery failure gets another shot on the next sweep.
_ACTIVE_COMM_STATUSES = frozenset({"queued", "sent"})


@dataclass
class PlannedReminder:
    billing_id: int
    bill_id: int
    offset_days: int
    comm_type: str
    recipient_count: int


@dataclass
class ReminderRunResult:
    bills_scanned: int = 0
    reminders_enqueued: int = 0  # (bill, offset) reminders actually sent
    recipients_notified: int = 0
    skipped_template_disabled: int = 0
    skipped_not_remindable_status: int = 0
    skipped_no_due_date: int = 0
    skipped_not_due_today: int = 0
    skipped_already_sent: int = 0
    skipped_no_recipients: int = 0
    skipped_no_pdf: int = 0
    planned: list[PlannedReminder] = field(default_factory=list)


class PaymentReminderService:
    def __init__(
        self,
        *,
        billing_repo,
        bill_repo,
        recipient_repo,
        communication_repo,
        communication_service: CommunicationService,
        channel: ReminderChannel,
        offset_days: list[int],
    ) -> None:
        self._billing_repo = billing_repo
        self._bill_repo = bill_repo
        self._recipient_repo = recipient_repo
        self._communication_repo = communication_repo
        self._communication_service = communication_service
        self._channel = channel
        self._offset_days = offset_days

    @traced("payment_reminder.run")
    def run(self, today: date, *, actor=None, dry_run: bool = False) -> ReminderRunResult:
        result = ReminderRunResult()
        for billing in self._billing_repo.list_all():
            if not billing.reminders_enabled:
                result.skipped_template_disabled += 1
                continue
            for bill in self._bill_repo.list_by_billing(billing.id):
                result.bills_scanned += 1
                self._process_bill(billing, bill, today, result, actor=actor, dry_run=dry_run)
        logger.info(
            "payment_reminder_sweep_done",
            today=today.isoformat(),
            dry_run=dry_run,
            channel=self._channel.name,
            bills_scanned=result.bills_scanned,
            reminders_enqueued=result.reminders_enqueued,
            recipients_notified=result.recipients_notified,
        )
        return result

    def _process_bill(
        self,
        billing: Billing,
        bill: Bill,
        today: date,
        result: ReminderRunResult,
        *,
        actor,
        dry_run: bool,
    ) -> None:
        if bill.status not in REMINDABLE_BILL_STATUSES:
            result.skipped_not_remindable_status += 1
            return

        offset = days_until_due(bill.due_date, today)
        if offset is None:
            result.skipped_no_due_date += 1
            return
        if offset not in self._offset_days:
            result.skipped_not_due_today += 1
            return

        comm_type = offset_comm_type(offset)
        if self._already_reminded(bill.id, comm_type):
            result.skipped_already_sent += 1
            return

        # The email channel re-attaches the invoice PDF (reusing communication.send),
        # which dead-letters without a rendered PDF. Skip until the PDF exists rather
        # than burn retries; the next sweep picks it up once rendered.
        if not bill.pdf_path:
            result.skipped_no_pdf += 1
            return

        recipients = self._recipient_repo.list_by_billing(billing.id)
        if not recipients:
            result.skipped_no_recipients += 1
            return

        result.planned.append(
            PlannedReminder(
                billing_id=billing.id,
                bill_id=bill.id,
                offset_days=offset,
                comm_type=comm_type,
                recipient_count=len(recipients),
            )
        )
        if dry_run:
            return

        template = self._communication_service.resolve_template(billing, REMINDER_TEMPLATE_COMM_TYPE)
        self._channel.send(
            bill=bill,
            billing=billing,
            recipients=recipients,
            comm_type=comm_type,
            subject_template=template.subject,
            body_template=template.body_markdown,
            actor=actor,
        )
        result.reminders_enqueued += 1
        result.recipients_notified += len(recipients)

    def _already_reminded(self, bill_id: int, comm_type: str) -> bool:
        for comm in self._communication_repo.list_by_bill(bill_id):
            if comm.comm_type == comm_type and comm.status in _ACTIVE_COMM_STATUSES:
                return True
        return False
