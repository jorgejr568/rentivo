"""Tests for export.send: resolve requester e-mail, download, mail once, enqueue s3.delete."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from rentivo.encryption.base64 import Base64Backend
from rentivo.jobs.base import PermanentJobError
from rentivo.models.billing import Billing
from rentivo.models.user import User
from rentivo.repositories.sqlalchemy.billing import SQLAlchemyBillingRepository
from rentivo.repositories.sqlalchemy.user import SQLAlchemyUserRepository
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


class _CapturingBackend:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return f"msg-{len(self.messages)}"


class _FakeStorage:
    def __init__(self, objects):
        self.objects = dict(objects)

    def get(self, key):
        return self.objects[key]


def _seed_user(engine, email="landlord@example.com"):
    with engine.connect() as c:
        return SQLAlchemyUserRepository(c, Base64Backend()).create(User(email=email, password_hash="x"))


def _seed_billing(engine, name="Apt 101"):
    with engine.connect() as c:
        return SQLAlchemyBillingRepository(c, Base64Backend()).create(Billing(name=name, owner_type="user", owner_id=1))


def _enqueued(engine, job_type):
    with engine.connect() as c:
        rows = c.execute(text("SELECT payload FROM jobs WHERE job_type = :t"), {"t": job_type}).fetchall()
    return [json.loads(r[0]) for r in rows]


def _patch(monkeypatch, engine, backend, storage):
    import rentivo.jobs.handlers.export as mod

    monkeypatch.setattr(mod, "get_engine", lambda: engine)
    monkeypatch.setattr(mod, "get_encryption", lambda: Base64Backend())
    monkeypatch.setattr(mod, "get_email_backend", lambda: backend)
    monkeypatch.setattr(mod, "get_storage", lambda: storage)


def _payload(user, billing, key="UUID/exports/abc.csv"):
    return {
        "storage_key": key,
        "content_type": "text/csv",
        "format": "csv",
        "bill_count": 3,
        "billing_id": billing.id,
        "requested_by_user_id": user.id,
    }


def test_sends_one_email_to_requesting_account(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_send

    user = _seed_user(engine, email="landlord@example.com")
    billing = _seed_billing(engine, name="São João")
    backend = _CapturingBackend()
    storage = _FakeStorage({"UUID/exports/abc.csv": b"Mes;Total\n"})
    _patch(monkeypatch, engine, backend, storage)

    handle_export_send(_payload(user, billing))

    assert len(backend.messages) == 1
    msg = backend.messages[0]
    assert msg.to == "landlord@example.com"
    att = msg.attachments[0]
    assert att.filename == "faturas_sao-joao.csv"
    assert att.content == b"Mes;Total\n"
    assert att.content_type == "text/csv"


def test_format_label_excel_for_xlsx(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_send

    user = _seed_user(engine)
    billing = _seed_billing(engine)
    backend = _CapturingBackend()
    storage = _FakeStorage({"k.xlsx": b"\x00"})
    _patch(monkeypatch, engine, backend, storage)

    payload = _payload(user, billing, key="k.xlsx")
    payload["format"] = "xlsx"
    payload["content_type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    handle_export_send(payload)

    msg = backend.messages[0]
    assert "Excel" in (msg.text_body or "") or "Excel" in (msg.html_body or "")


def test_enqueues_s3_delete_after_send(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_send

    user = _seed_user(engine)
    billing = _seed_billing(engine)
    backend = _CapturingBackend()
    storage = _FakeStorage({"UUID/exports/abc.csv": b"x"})
    _patch(monkeypatch, engine, backend, storage)

    handle_export_send(_payload(user, billing))

    deletes = _enqueued(engine, "s3.delete")
    assert len(deletes) == 1
    assert deletes[0]["key"] == "UUID/exports/abc.csv"


def test_unknown_user_raises_permanent(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_send

    billing = _seed_billing(engine)
    backend = _CapturingBackend()
    storage = _FakeStorage({"UUID/exports/abc.csv": b"x"})
    _patch(monkeypatch, engine, backend, storage)

    payload = {
        "storage_key": "UUID/exports/abc.csv",
        "content_type": "text/csv",
        "format": "csv",
        "bill_count": 1,
        "billing_id": billing.id,
        "requested_by_user_id": 99999,
    }
    with pytest.raises(PermanentJobError):
        handle_export_send(payload)
    assert backend.messages == []


def test_unknown_billing_raises_permanent(engine, monkeypatch):
    from rentivo.jobs.handlers.export import handle_export_send

    user = _seed_user(engine)
    backend = _CapturingBackend()
    storage = _FakeStorage({"UUID/exports/abc.csv": b"x"})
    _patch(monkeypatch, engine, backend, storage)

    payload = {
        "storage_key": "UUID/exports/abc.csv",
        "content_type": "text/csv",
        "format": "csv",
        "bill_count": 1,
        "billing_id": 99999,
        "requested_by_user_id": user.id,
    }
    with pytest.raises(PermanentJobError):
        handle_export_send(payload)
    assert backend.messages == []
