from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from rentivo.communications.defaults import DEFAULT_BILL_READY_BODY
from rentivo.encryption.base64 import Base64Backend
from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.recipient import Recipient
from rentivo.repositories.sqlalchemy.communication import (
    SQLAlchemyCommunicationRepository,
    SQLAlchemyCommunicationTemplateRepository,
)
from rentivo.services.communication_service import CommunicationService
from tests.conftest import SCHEMA_DDL


class _FakeJobService:
    def __init__(self):
        self.enqueued = []

    def enqueue_for(self, actor, job_type, payload, *, max_attempts=5):
        self.enqueued.append((job_type, payload))

        class _Job:
            ulid = "01JOBULID0000000000000000"

        return _Job()


@pytest.fixture()
def ctx():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with eng.connect() as c:
        for stmt in SCHEMA_DDL.strip().split(";"):
            if stmt.strip():
                c.execute(text(stmt))
        c.commit()
        job = _FakeJobService()
        service = CommunicationService(
            communication_repo=SQLAlchemyCommunicationRepository(c, Base64Backend()),
            template_repo=SQLAlchemyCommunicationTemplateRepository(c, Base64Backend()),
            job_service=job,
        )
        yield service, job, c


def _billing():
    return Billing(id=1, uuid="BILLINGUUID", name="Joy 105 Bloco 2", owner_type="user", owner_id=7)


def _bill():
    return Bill(
        id=5,
        uuid="BILLUUID",
        billing_id=1,
        reference_month="2026-05",
        total_amount=128500,
        due_date="10/06/2026",
    )


def test_resolve_template_falls_back_to_system_default(ctx):
    service, _job, _c = ctx
    tmpl = service.resolve_template(_billing(), "bill_ready")
    assert tmpl.owner_type == "system"
    assert tmpl.body_markdown == DEFAULT_BILL_READY_BODY


def test_resolve_template_prefers_billing_over_owner(ctx):
    service, _job, _c = ctx
    service.save_template("user", 7, "bill_ready", "User S", "User B")
    service.save_template("billing", 1, "bill_ready", "Billing S", "Billing B")
    tmpl = service.resolve_template(_billing(), "bill_ready")
    assert tmpl.owner_type == "billing"
    assert tmpl.subject == "Billing S"


def test_resolve_template_uses_owner_when_no_billing_template(ctx):
    service, _job, _c = ctx
    service.save_template("user", 7, "bill_ready", "User S", "User B")
    tmpl = service.resolve_template(_billing(), "bill_ready")
    assert tmpl.owner_type == "user"


def test_send_creates_one_communication_per_recipient_and_enqueues(ctx):
    service, job, _c = ctx
    recipients = [
        Recipient(billing_id=1, name="João", email="joao@example.com"),
        Recipient(billing_id=1, name="Ana", email="ana@example.com"),
    ]
    comms = service.send(
        bill=_bill(),
        billing=_billing(),
        recipients=recipients,
        subject_template="Cobrança {{unidade}} — {{mes}}",
        body_template="Prezado {{nome_inquilino}}, unidade {{unidade}}, mês {{mes}}, total {{total}}.",
        actor=None,
    )
    assert len(comms) == 2
    assert len(job.enqueued) == 2
    assert job.enqueued[0][0] == "communication.send"
    first = comms[0]
    assert first.subject == "Cobrança Joy 105 Bloco 2 — maio de 2026"
    assert "Prezado João" in first.body_markdown
    assert "R$ 1.285,00" in first.body_markdown
    assert first.status == "queued"
    assert first.job_ulid == "01JOBULID0000000000000000"


def test_send_defaults_comm_type_to_bill_ready(ctx):
    service, _job, _c = ctx
    comms = service.send(
        _bill(), _billing(), [Recipient(billing_id=1, name="R", email="r@x.com")], "s", "b", actor=None
    )
    assert comms[0].comm_type == "bill_ready"


def test_send_honors_payment_receipt_comm_type(ctx):
    service, job, _c = ctx
    comms = service.send(
        _bill(),
        _billing(),
        [Recipient(billing_id=1, name="R", email="r@x.com")],
        "Recibo {{unidade}}",
        "Segue o recibo de {{total}}.",
        actor=None,
        comm_type="payment_receipt",
    )
    assert comms[0].comm_type == "payment_receipt"
    assert "R$ 1.285,00" in comms[0].body_markdown
    assert job.enqueued[0][0] == "communication.send"


def test_send_with_no_recipients_returns_empty(ctx):
    service, job, _c = ctx
    assert service.send(_bill(), _billing(), [], "s", "b", actor=None) == []
    assert job.enqueued == []


def test_list_for_bill(ctx):
    service, _job, _c = ctx
    service.send(_bill(), _billing(), [Recipient(billing_id=1, name="R", email="r@x.com")], "s", "b", actor=None)
    assert len(service.list_for_bill(5)) == 1


def test_send_marks_failed_and_reraises_when_enqueue_fails(ctx):
    """If enqueue raises, the just-created row is marked 'failed' (not left a stuck
    'queued' orphan with no job) and the error propagates."""
    _service, _job, c = ctx

    class _BoomJobService:
        def enqueue_for(self, *a, **k):
            raise RuntimeError("queue down")

    service = CommunicationService(
        communication_repo=SQLAlchemyCommunicationRepository(c, Base64Backend()),
        template_repo=SQLAlchemyCommunicationTemplateRepository(c, Base64Backend()),
        job_service=_BoomJobService(),
    )
    with pytest.raises(RuntimeError):
        service.send(_bill(), _billing(), [Recipient(billing_id=1, name="R", email="r@x.com")], "s", "b", actor=None)

    rows = SQLAlchemyCommunicationRepository(c, Base64Backend()).list_by_bill(5)
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].job_ulid == ""
