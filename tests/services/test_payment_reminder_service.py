from __future__ import annotations

from datetime import date

import pytest

from rentivo.models.bill import Bill, BillStatus
from rentivo.models.billing import Billing
from rentivo.models.communication import Communication, CommunicationTemplate
from rentivo.models.recipient import Recipient
from rentivo.services.payment_reminder_service import PaymentReminderService

TODAY = date(2026, 6, 10)


class _FakeBillingRepo:
    def __init__(self, billings):
        self._billings = billings

    def list_all(self):
        return list(self._billings)


class _FakeBillRepo:
    def __init__(self, by_billing):
        self._by_billing = by_billing

    def list_by_billing(self, billing_id):
        return list(self._by_billing.get(billing_id, []))


class _FakeRecipientRepo:
    def __init__(self, by_billing):
        self._by_billing = by_billing

    def list_by_billing(self, billing_id):
        return list(self._by_billing.get(billing_id, []))


class _FakeCommRepo:
    def __init__(self, by_bill=None):
        self._by_bill = by_bill or {}

    def list_by_bill(self, bill_id):
        return list(self._by_bill.get(bill_id, []))


class _FakeCommService:
    def resolve_template(self, billing, comm_type):
        return CommunicationTemplate(
            owner_type="system",
            owner_id=0,
            comm_type=comm_type,
            subject="Lembrete {{unidade}}",
            body_markdown="Vence {{vencimento}} — {{total}}",
        )


class _FakeChannel:
    name = "email"

    def __init__(self):
        self.calls = []

    def send(self, *, bill, billing, recipients, comm_type, subject_template, body_template, actor=None):
        self.calls.append(
            {
                "bill_id": bill.id,
                "billing_id": billing.id,
                "comm_type": comm_type,
                "recipients": list(recipients),
            }
        )
        return [
            Communication(
                bill_id=bill.id,
                comm_type=comm_type,
                recipient_name=r.name,
                recipient_email=r.email,
                subject="Lembrete",
                body_markdown="corpo",
            )
            for r in recipients
        ]


def _billing(billing_id=1, reminders_enabled=True):
    return Billing(
        id=billing_id,
        uuid=f"B{billing_id}",
        name="Apto 101",
        owner_type="user",
        owner_id=7,
        reminders_enabled=reminders_enabled,
    )


def _bill(bill_id=5, billing_id=1, *, due_date="13/06/2026", status=BillStatus.SENT.value, pdf_path="bills/5.pdf"):
    return Bill(
        id=bill_id,
        uuid=f"BILL{bill_id}",
        billing_id=billing_id,
        reference_month="2026-06",
        total_amount=128500,
        due_date=due_date,
        status=status,
        pdf_path=pdf_path,
    )


def _recipient(billing_id=1, name="Inquilino", email="t@example.com"):
    return Recipient(billing_id=billing_id, name=name, email=email)


def _service(*, billings, bills, recipients, comms=None, offsets=(3, 0, -3), channel=None):
    channel = channel or _FakeChannel()
    svc = PaymentReminderService(
        billing_repo=_FakeBillingRepo(billings),
        bill_repo=_FakeBillRepo(bills),
        recipient_repo=_FakeRecipientRepo(recipients),
        communication_repo=_FakeCommRepo(comms),
        communication_service=_FakeCommService(),
        channel=channel,
        offset_days=list(offsets),
    )
    return svc, channel


def test_sends_reminder_for_unpaid_bill_on_offset():
    svc, channel = _service(
        billings=[_billing()],
        bills={1: [_bill(due_date="13/06/2026")]},  # 3 days before due
        recipients={1: [_recipient()]},
    )
    result = svc.run(TODAY)
    assert len(channel.calls) == 1
    assert channel.calls[0]["comm_type"] == "payment_reminder:d-3"
    assert result.reminders_enqueued == 1
    assert result.recipients_notified == 1


def test_paid_bill_is_skipped():
    svc, channel = _service(
        billings=[_billing()],
        bills={1: [_bill(status=BillStatus.PAID.value)]},
        recipients={1: [_recipient()]},
    )
    result = svc.run(TODAY)
    assert channel.calls == []
    assert result.skipped_not_remindable_status == 1


def test_disabled_template_is_skipped():
    svc, channel = _service(
        billings=[_billing(reminders_enabled=False)],
        bills={1: [_bill()]},
        recipients={1: [_recipient()]},
    )
    result = svc.run(TODAY)
    assert channel.calls == []
    assert result.skipped_template_disabled == 1


def test_already_sent_offset_is_deduped():
    existing = Communication(
        bill_id=5,
        comm_type="payment_reminder:d-3",
        recipient_name="x",
        recipient_email="x@e.com",
        subject="s",
        body_markdown="b",
        status="sent",
    )
    svc, channel = _service(
        billings=[_billing()],
        bills={1: [_bill(due_date="13/06/2026")]},
        recipients={1: [_recipient()]},
        comms={5: [existing]},
    )
    result = svc.run(TODAY)
    assert channel.calls == []
    assert result.skipped_already_sent == 1


def test_failed_reminder_is_retried():
    failed = Communication(
        bill_id=5,
        comm_type="payment_reminder:d-3",
        recipient_name="x",
        recipient_email="x@e.com",
        subject="s",
        body_markdown="b",
        status="failed",
    )
    svc, channel = _service(
        billings=[_billing()],
        bills={1: [_bill(due_date="13/06/2026")]},
        recipients={1: [_recipient()]},
        comms={5: [failed]},
    )
    result = svc.run(TODAY)
    assert len(channel.calls) == 1
    assert result.reminders_enqueued == 1


def test_bill_not_in_offset_window_is_skipped():
    svc, channel = _service(
        billings=[_billing()],
        bills={1: [_bill(due_date="20/06/2026")]},  # 10 days out, not in {3,0,-3}
        recipients={1: [_recipient()]},
    )
    result = svc.run(TODAY)
    assert channel.calls == []
    assert result.skipped_not_due_today == 1


def test_unparseable_due_date_is_skipped():
    svc, channel = _service(
        billings=[_billing()],
        bills={1: [_bill(due_date="qualquer dia")]},
        recipients={1: [_recipient()]},
    )
    result = svc.run(TODAY)
    assert channel.calls == []
    assert result.skipped_no_due_date == 1


def test_bill_without_pdf_is_skipped():
    svc, channel = _service(
        billings=[_billing()],
        bills={1: [_bill(due_date="10/06/2026", pdf_path=None)]},
        recipients={1: [_recipient()]},
    )
    result = svc.run(TODAY)
    assert channel.calls == []
    assert result.skipped_no_pdf == 1


def test_no_recipients_is_skipped():
    svc, channel = _service(
        billings=[_billing()],
        bills={1: [_bill(due_date="10/06/2026")]},
        recipients={1: []},
    )
    result = svc.run(TODAY)
    assert channel.calls == []
    assert result.skipped_no_recipients == 1


def test_dry_run_plans_without_sending():
    svc, channel = _service(
        billings=[_billing()],
        bills={1: [_bill(due_date="10/06/2026")]},  # due today
        recipients={1: [_recipient(), _recipient(email="b@e.com")]},
    )
    result = svc.run(TODAY, dry_run=True)
    assert channel.calls == []
    assert len(result.planned) == 1
    assert result.planned[0].offset_days == 0
    assert result.planned[0].comm_type == "payment_reminder:due"
    assert result.planned[0].recipient_count == 2
    assert result.reminders_enqueued == 0


def test_multiple_recipients_all_notified():
    svc, channel = _service(
        billings=[_billing()],
        bills={1: [_bill(due_date="07/06/2026")]},  # 3 days overdue -> d+3
        recipients={1: [_recipient(email="a@e.com"), _recipient(email="b@e.com")]},
    )
    result = svc.run(TODAY)
    assert len(channel.calls) == 1
    assert channel.calls[0]["comm_type"] == "payment_reminder:d+3"
    assert result.recipients_notified == 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
