"""Tests for export.generate: build the file, upload to storage, enqueue export.send."""

from __future__ import annotations

import io
import json

import openpyxl
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from rentivo.encryption.base64 import Base64Backend
from rentivo.jobs.base import PermanentJobError
from rentivo.models.billing import Billing
from rentivo.repositories.sqlalchemy.billing import SQLAlchemyBillingRepository
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


class _FakeStorage:
    """Captures save() calls and serves them back from get()."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def save(self, key, data, content_type="application/octet-stream"):
        self.objects[key] = data
        return key

    def get(self, key):
        return self.objects[key]


def _seed_billing(engine, name="Apt 101"):
    with engine.connect() as c:
        return SQLAlchemyBillingRepository(c, Base64Backend()).create(Billing(name=name, owner_type="user", owner_id=1))


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


def _enqueued(engine, job_type):
    with engine.connect() as c:
        rows = c.execute(text("SELECT payload FROM jobs WHERE job_type = :t"), {"t": job_type}).fetchall()
    return [json.loads(r[0]) for r in rows]


def _patch(monkeypatch, engine, storage):
    import rentivo.jobs.handlers.export as mod

    monkeypatch.setattr(mod, "get_engine", lambda: engine)
    monkeypatch.setattr(mod, "get_encryption", lambda: Base64Backend())
    monkeypatch.setattr(mod, "get_storage", lambda: storage)


def test_uploads_csv_and_enqueues_export_send(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_generate

    billing = _seed_billing(engine, name="São João")
    _add_bill(engine, billing)
    storage = _FakeStorage()
    _patch(monkeypatch, engine, storage)

    handle_export_generate({"billing_id": billing.id, "format": "csv", "requested_by_user_id": 7})

    assert len(storage.objects) == 1
    key = next(iter(storage.objects))
    assert key.startswith(f"{billing.uuid}/exports/")
    assert key.endswith(".csv")
    body = storage.objects[key].decode("utf-8-sig")
    assert "Mês de referência" in body
    assert "São João" in body

    sends = _enqueued(engine, "export.send")
    assert len(sends) == 1
    assert sends[0]["storage_key"] == key
    assert sends[0]["format"] == "csv"
    assert sends[0]["content_type"] == "text/csv"
    assert sends[0]["bill_count"] == 1
    assert sends[0]["billing_id"] == billing.id
    assert sends[0]["requested_by_user_id"] == 7


def test_uploads_xlsx(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_generate

    billing = _seed_billing(engine)
    _add_bill(engine, billing)
    storage = _FakeStorage()
    _patch(monkeypatch, engine, storage)

    handle_export_generate({"billing_id": billing.id, "format": "xlsx", "requested_by_user_id": 1})

    key = next(iter(storage.objects))
    assert key.endswith(".xlsx")
    ws = openpyxl.load_workbook(io.BytesIO(storage.objects[key])).active
    assert ws["A1"].value == "Mês de referência"
    sends = _enqueued(engine, "export.send")
    assert sends[0]["content_type"].endswith("spreadsheetml.sheet")
    assert sends[0]["format"] == "xlsx"


def test_empty_billing_still_uploads_header_only(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_generate

    billing = _seed_billing(engine)
    storage = _FakeStorage()
    _patch(monkeypatch, engine, storage)

    handle_export_generate({"billing_id": billing.id, "format": "csv", "requested_by_user_id": 1})

    key = next(iter(storage.objects))
    lines = storage.objects[key].decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Mês de referência")
    assert len(lines) == 1
    assert len(_enqueued(engine, "export.send")) == 1


def test_billing_not_found_raises_permanent(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_generate

    storage = _FakeStorage()
    _patch(monkeypatch, engine, storage)
    with pytest.raises(PermanentJobError):
        handle_export_generate({"billing_id": 99999, "format": "csv", "requested_by_user_id": 1})
    assert storage.objects == {}


def test_non_int_billing_id_raises_permanent():
    from rentivo.jobs.handlers.export import handle_export_generate

    with pytest.raises(PermanentJobError):
        handle_export_generate({"billing_id": "x", "format": "csv", "requested_by_user_id": 1})
