"""Reconcile inbound PSP payment webhooks against bills (REN-26).

This is the server-side half of the Asaas dynamic-PIX auto-confirmation pilot.
The :class:`~rentivo.services.asaas_pix_service.AsaasPixService` authenticates
and normalizes the webhook; this service decides what it *means* for a bill and
drives the (idempotent, audited) transition to ``PAID``.

Flow (one public webhook delivery):

1. **Idempotency / replay drop** — record ``(provider, event_id)`` in the
   ``pix_webhook_events`` ledger. A duplicate delivery loses the unique-key
   race and is dropped as a no-op (``DUPLICATE``).
2. **Paid filter** — only ``PAYMENT_RECEIVED`` / ``PAYMENT_CONFIRMED`` events
   move money; everything else is recorded and ignored (``IGNORED_NOT_PAID``).
3. **Reconciliation key** — look up the bill by ``external_reference ==
   bill.uuid``. Unknown reference → ``BILL_NOT_FOUND`` (recorded, acked).
4. **Amount cross-check** — if the event amount disagrees with the bill total,
   refuse to transition (``AMOUNT_MISMATCH``) and leave it for a human.
5. **Transition** — call ``bill_service.change_status(bill, PAID)`` (the same
   single chokepoint the manual UI uses), persist the PSP linkage / e2eid, and
   audit the change as actor ``system/psp-webhook``.

Already-``PAID`` bills are treated as success (``ALREADY_PAID``) so a settled
event that arrives after a manual confirmation does not error.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import structlog

from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import BillStatus
from rentivo.observability import traced
from rentivo.repositories.base import BillRepository, PixWebhookEventRepository
from rentivo.services.asaas_pix_service import PixPaymentEvent
from rentivo.services.audit_service import AuditService
from rentivo.services.bill_service import BillService

logger = structlog.get_logger(__name__)

# Actor recorded on the audit row for a webhook-driven transition. Not a real
# user; the audit log's actor_id stays NULL and the username carries the source.
WEBHOOK_ACTOR_USERNAME = "system/psp-webhook"
WEBHOOK_ACTOR_SOURCE = "psp-webhook"


class ReconcileOutcome(str, Enum):
    CONFIRMED = "confirmed"  # bill moved to PAID by this delivery
    ALREADY_PAID = "already_paid"  # bill was already PAID (no-op success)
    DUPLICATE = "duplicate"  # replayed event_id — dropped
    IGNORED_NOT_PAID = "ignored_not_paid"  # recorded, but not a paid event
    BILL_NOT_FOUND = "bill_not_found"  # no bill for external_reference
    AMOUNT_MISMATCH = "amount_mismatch"  # event amount != bill total


@dataclass(frozen=True)
class ReconcileResult:
    outcome: ReconcileOutcome
    bill_uuid: str | None = None
    detail: str | None = None


class PixReconciliationService:
    def __init__(
        self,
        *,
        bill_service: BillService,
        bill_repo: BillRepository,
        webhook_event_repo: PixWebhookEventRepository,
        audit_service: AuditService,
        provider_name: str = "asaas",
    ) -> None:
        self._bills = bill_service
        self._bill_repo = bill_repo
        self._events = webhook_event_repo
        self._audit = audit_service
        self._provider = provider_name

    @traced("pix_reconciliation.confirm")
    def confirm_payment(self, event: PixPaymentEvent) -> ReconcileResult:
        """Idempotently reconcile one normalized payment event against a bill."""
        # 1. Idempotency / replay guard. Recording first (before any side effect)
        #    means concurrent duplicate deliveries can never both transition the
        #    bill — only the row that wins the unique-key race proceeds.
        is_new = self._events.record_if_new(
            provider=self._provider,
            event_id=event.event_id,
            event_type=event.event_type,
            status=event.status,
            charge_id=event.charge_id or None,
            external_reference=event.external_reference or None,
            e2eid=event.e2eid,
        )
        if not is_new:
            logger.info("pix_webhook_replay_dropped", provider=self._provider, event_id=event.event_id)
            return ReconcileResult(ReconcileOutcome.DUPLICATE)

        # 2. Only genuine cash-in events move a bill. Anything else is now
        #    recorded (for audit/debug) and acked without further action.
        if not event.is_paid:
            logger.info(
                "pix_webhook_non_paid_event",
                provider=self._provider,
                event_type=event.event_type,
                charge_id=event.charge_id,
            )
            return ReconcileResult(ReconcileOutcome.IGNORED_NOT_PAID, detail=event.event_type)

        # 3. Reconciliation key: external_reference == bill.uuid.
        bill = self._bills.get_bill_by_uuid(event.external_reference) if event.external_reference else None
        if bill is None or bill.id is None:
            logger.warning(
                "pix_webhook_bill_not_found",
                provider=self._provider,
                external_reference=event.external_reference,
                charge_id=event.charge_id,
            )
            return ReconcileResult(ReconcileOutcome.BILL_NOT_FOUND, detail=event.external_reference)

        self._events.set_bill_id(provider=self._provider, event_id=event.event_id, bill_id=bill.id)

        # 4. Defensive amount cross-check. A mismatch is a reconciliation
        #    anomaly, not a transition — leave the bill for a human.
        if event.amount_centavos and event.amount_centavos != bill.total_amount:
            logger.warning(
                "pix_webhook_amount_mismatch",
                bill_uuid=bill.uuid,
                event_amount_centavos=event.amount_centavos,
                bill_total_centavos=bill.total_amount,
            )
            return ReconcileResult(
                ReconcileOutcome.AMOUNT_MISMATCH,
                bill_uuid=bill.uuid,
                detail=f"event={event.amount_centavos} bill={bill.total_amount}",
            )

        # Persist PSP linkage (provider/charge/e2eid) regardless of prior status.
        self._bill_repo.update_pix_linkage(
            bill.id,
            provider=self._provider,
            charge_id=event.charge_id or None,
            e2eid=event.e2eid,
        )

        # 5. Idempotent transition through the single chokepoint. A bill already
        #    PAID (e.g. confirmed manually first) is a no-op success.
        if bill.status == BillStatus.PAID.value:
            logger.info("pix_webhook_bill_already_paid", bill_uuid=bill.uuid, charge_id=event.charge_id)
            return ReconcileResult(ReconcileOutcome.ALREADY_PAID, bill_uuid=bill.uuid)

        previous_status = bill.status
        self._bills.change_status(bill, BillStatus.PAID.value)

        self._audit.safe_log(
            AuditEventType.BILL_STATUS_CHANGE,
            actor_id=None,
            actor_username=WEBHOOK_ACTOR_USERNAME,
            source=WEBHOOK_ACTOR_SOURCE,
            entity_type="bill",
            entity_id=bill.id,
            entity_uuid=bill.uuid,
            previous_state={"status": previous_status},
            new_state={"status": BillStatus.PAID.value},
            metadata={
                "provider": self._provider,
                "event_id": event.event_id,
                "event_type": event.event_type,
                "charge_id": event.charge_id,
                "e2eid": event.e2eid,
            },
        )
        logger.info(
            "pix_webhook_bill_confirmed",
            bill_uuid=bill.uuid,
            provider=self._provider,
            charge_id=event.charge_id,
            e2eid=event.e2eid,
        )
        return ReconcileResult(ReconcileOutcome.CONFIRMED, bill_uuid=bill.uuid)
