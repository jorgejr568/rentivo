"""Tests for the export.generate worker handler (file built + emailed to recipients)."""

from __future__ import annotations

import io

import openpyxl
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from rentivo.encryption.base64 import Base64Backend
from rentivo.jobs.base import PermanentJobError
from rentivo.models.billing import Billing
from rentivo.models.recipient import Recipient
from rentivo.repositories.sqlalchemy.billing import SQLAlchemyBillingRepository
from rentivo.repositories.sqlalchemy.recipient import SQLAlchemyRecipientRepository
from tests.conftest import SCHEMA_DDL


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with eng.connect() as c:
        for stmt in SCHEMA_DDL.strip().split(";"):
            if stmt.strip():
                c.execute(text(stmt))
        c.commit()
    return eng


def _seed_billing(engine, name="Apt 101"):
    with engine.connect() as c:
        return SQLAlchemyBillingRepository(c, Base64Backend()).create(Billing(name=name, owner_type="user", owner_id=1))


def _add_recipients(engine, billing, recipients):
    with engine.connect() as c:
        SQLAlchemyRecipientRepository(c, Base64Backend()).replace_for_billing(billing.id, recipients)


def _add_bill(engine, billing, reference_month="2025-03", total_amount=285050):
    with engine.connect() as c:
        c.execute(
            text(
                "INSERT INTO bills (uuid, billing_id, reference_month, total_amount, status, due_date, created_at) "
                "VALUES (:u, :b, :rm, :amt, 'paid', '10/04/2025', '2025-03-01')"
            ),
            {"u": f"BILL{reference_month}", "b": billing.id, "rm": reference_month, "amt": total_amount},
        )
        c.commit()


class _CapturingBackend:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return f"msg-{len(self.messages)}"


def _patch(monkeypatch, engine, backend):
    import rentivo.jobs.handlers.export as mod

    monkeypatch.setattr(mod, "get_engine", lambda: engine)
    monkeypatch.setattr(mod, "get_encryption", lambda: Base64Backend())
    monkeypatch.setattr(mod, "get_email_backend", lambda: backend)


def test_sends_csv_attachment_to_each_recipient(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_generate

    billing = _seed_billing(engine, name="São João")
    _add_bill(engine, billing)
    _add_recipients(
        engine,
        billing,
        [
            Recipient(billing_id=billing.id, name="Ana", email="ana@example.com"),
            Recipient(billing_id=billing.id, name="Bruno", email="bruno@example.com"),
        ],
    )
    backend = _CapturingBackend()
    _patch(monkeypatch, engine, backend)

    handle_export_generate({"billing_id": billing.id, "format": "csv"})

    assert {m.to for m in backend.messages} == {"ana@example.com", "bruno@example.com"}
    att = backend.messages[0].attachments[0]
    assert att.filename == "faturas_sao-joao.csv"
    assert att.content_type == "text/csv"
    text_body = att.content.decode("utf-8-sig")
    assert "Mês de referência" in text_body
    assert "São João" in text_body


def test_sends_xlsx_attachment(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_generate

    billing = _seed_billing(engine)
    _add_bill(engine, billing)
    _add_recipients(engine, billing, [Recipient(billing_id=billing.id, name="Ana", email="ana@example.com")])
    backend = _CapturingBackend()
    _patch(monkeypatch, engine, backend)

    handle_export_generate({"billing_id": billing.id, "format": "xlsx"})

    att = backend.messages[0].attachments[0]
    assert att.filename == "faturas_apt-101.xlsx"
    assert att.content_type.endswith("spreadsheetml.sheet")
    ws = openpyxl.load_workbook(io.BytesIO(att.content)).active
    assert ws["A1"].value == "Mês de referência"


def test_subject_includes_billing_name(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_generate

    billing = _seed_billing(engine, name="Cobertura")
    _add_bill(engine, billing)
    _add_recipients(engine, billing, [Recipient(billing_id=billing.id, name="Ana", email="ana@example.com")])
    backend = _CapturingBackend()
    _patch(monkeypatch, engine, backend)

    handle_export_generate({"billing_id": billing.id, "format": "csv"})

    assert "Cobertura" in backend.messages[0].subject


def test_no_recipients_sends_nothing(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_generate

    billing = _seed_billing(engine)
    _add_bill(engine, billing)
    backend = _CapturingBackend()
    _patch(monkeypatch, engine, backend)

    handle_export_generate({"billing_id": billing.id, "format": "csv"})

    assert backend.messages == []


def test_empty_billing_still_sends_header_only_file(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_generate

    billing = _seed_billing(engine)
    _add_recipients(engine, billing, [Recipient(billing_id=billing.id, name="Ana", email="ana@example.com")])
    backend = _CapturingBackend()
    _patch(monkeypatch, engine, backend)

    handle_export_generate({"billing_id": billing.id, "format": "csv"})

    assert len(backend.messages) == 1
    lines = backend.messages[0].attachments[0].content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Mês de referência")
    assert len(lines) == 1


def test_billing_not_found_raises_permanent(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_generate

    backend = _CapturingBackend()
    _patch(monkeypatch, engine, backend)
    with pytest.raises(PermanentJobError):
        handle_export_generate({"billing_id": 99999, "format": "csv"})


def test_non_int_billing_id_raises_permanent():
    from rentivo.jobs.handlers.export import handle_export_generate

    with pytest.raises(PermanentJobError):
        handle_export_generate({"billing_id": "x", "format": "csv"})
