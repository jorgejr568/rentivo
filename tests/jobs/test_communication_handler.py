from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from rentivo.encryption.base64 import Base64Backend
from rentivo.jobs.base import PermanentJobError
from rentivo.models.communication import Communication
from rentivo.repositories.sqlalchemy.communication import SQLAlchemyCommunicationRepository
from tests.conftest import SCHEMA_DDL


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with eng.connect() as c:
        for stmt in SCHEMA_DDL.strip().split(";"):
            if stmt.strip():
                c.execute(text(stmt))
        # A bill with a pdf_path so the handler can fetch PDF bytes.
        c.execute(
            text(
                "INSERT INTO bills (id, uuid, billing_id, reference_month, total_amount, pdf_path, status, created_at) "
                "VALUES (5, 'BILLUUID', 1, '2026-05', 100000, 'k/bill.pdf', 'published', '2026-05-01')"
            )
        )
        c.commit()
    return eng


def _seed_comm(engine):
    with engine.connect() as c:
        repo = SQLAlchemyCommunicationRepository(c, Base64Backend())
        return repo.create(
            Communication(
                bill_id=5,
                comm_type="bill_ready",
                recipient_name="Rodrigo",
                recipient_email="rodrigo@example.com",
                subject="Cobrança",
                body_markdown="Prezado **Rodrigo**",
            )
        )


def test_handler_sends_and_marks_sent(engine, monkeypatch, tmp_path):
    import rentivo.jobs.handlers.communication as mod
    from rentivo.jobs.handlers.communication import handle_communication_send

    comm = _seed_comm(engine)
    sent = {}

    class FakeStorage:
        def get(self, key):
            return b"%PDF-1.4 fake"

    class FakeBackend:
        def send(self, message):
            sent["msg"] = message
            return "msg-1"

    monkeypatch.setattr(mod, "get_engine", lambda: engine)
    monkeypatch.setattr(mod, "get_encryption", lambda: Base64Backend())
    monkeypatch.setattr(mod, "get_storage", lambda: FakeStorage())
    monkeypatch.setattr(mod, "get_email_backend", lambda: FakeBackend())

    handle_communication_send({"communication_id": comm.id})

    assert sent["msg"].to == "rodrigo@example.com"
    assert sent["msg"].attachments[0].content == b"%PDF-1.4 fake"
    assert "<strong>Rodrigo</strong>" in sent["msg"].html_body

    with engine.connect() as c:
        repo = SQLAlchemyCommunicationRepository(c, Base64Backend())
        assert repo.get_by_id(comm.id).status == "sent"


def test_handler_sets_reply_to_and_from_override(engine, monkeypatch):
    import rentivo.jobs.handlers.communication as mod
    from rentivo.jobs.handlers.communication import handle_communication_send
    from rentivo.models.recipient import Recipient
    from rentivo.repositories.sqlalchemy.reply_to import SQLAlchemyReplyToRecipientRepository

    comm = _seed_comm(engine)
    with engine.connect() as c:
        SQLAlchemyReplyToRecipientRepository(c, Base64Backend()).replace_for_billing(
            1,
            [
                Recipient(billing_id=1, name="Ana", email="ana@example.com"),
                Recipient(billing_id=1, name="", email="bruno@example.com"),
            ],
        )

    sent = {}

    class FakeStorage:
        def get(self, key):
            return b"%PDF-1.4 fake"

    class FakeBackend:
        def send(self, message):
            sent["msg"] = message
            return "msg-1"

    monkeypatch.setattr(mod, "get_engine", lambda: engine)
    monkeypatch.setattr(mod, "get_encryption", lambda: Base64Backend())
    monkeypatch.setattr(mod, "get_storage", lambda: FakeStorage())
    monkeypatch.setattr(mod, "get_email_backend", lambda: FakeBackend())
    monkeypatch.setattr(mod.settings, "communications_from_email", "cobranca@example.com", raising=False)

    handle_communication_send({"communication_id": comm.id})

    assert sent["msg"].from_address == "cobranca@example.com"
    assert sent["msg"].reply_to == ("Ana <ana@example.com>", "bruno@example.com")


def test_handler_no_reply_to_and_no_from_override(engine, monkeypatch):
    import rentivo.jobs.handlers.communication as mod
    from rentivo.jobs.handlers.communication import handle_communication_send

    comm = _seed_comm(engine)
    sent = {}

    class FakeStorage:
        def get(self, key):
            return b"%PDF"

    class FakeBackend:
        def send(self, message):
            sent["msg"] = message
            return "msg-1"

    monkeypatch.setattr(mod, "get_engine", lambda: engine)
    monkeypatch.setattr(mod, "get_encryption", lambda: Base64Backend())
    monkeypatch.setattr(mod, "get_storage", lambda: FakeStorage())
    monkeypatch.setattr(mod, "get_email_backend", lambda: FakeBackend())
    monkeypatch.setattr(mod.settings, "communications_from_email", "", raising=False)
    monkeypatch.setattr(mod.settings, "ses_from_email", "", raising=False)

    handle_communication_send({"communication_id": comm.id})

    assert sent["msg"].reply_to == ()
    assert sent["msg"].from_address == "noreply@localhost"


def test_handler_rejects_non_int_id():
    from rentivo.jobs.handlers.communication import handle_communication_send

    with pytest.raises(PermanentJobError):
        handle_communication_send({"communication_id": "x"})


def test_handler_permanent_error_when_communication_missing(engine, monkeypatch):
    import rentivo.jobs.handlers.communication as mod
    from rentivo.jobs.handlers.communication import handle_communication_send

    monkeypatch.setattr(mod, "get_engine", lambda: engine)
    monkeypatch.setattr(mod, "get_encryption", lambda: Base64Backend())
    with pytest.raises(PermanentJobError):
        handle_communication_send({"communication_id": 99999})


def test_handler_permanent_error_when_pdf_missing(engine, monkeypatch):
    import rentivo.jobs.handlers.communication as mod
    from rentivo.jobs.handlers.communication import handle_communication_send

    comm = _seed_comm(engine)
    with engine.connect() as c:
        c.execute(text("UPDATE bills SET pdf_path = NULL WHERE id = 5"))
        c.commit()
    monkeypatch.setattr(mod, "get_engine", lambda: engine)
    monkeypatch.setattr(mod, "get_encryption", lambda: Base64Backend())
    with pytest.raises(PermanentJobError):
        handle_communication_send({"communication_id": comm.id})


def test_handler_skips_already_sent_communication(engine, monkeypatch):
    """A retry of an already-delivered communication must not re-send the email."""
    from datetime import datetime

    import rentivo.jobs.handlers.communication as mod
    from rentivo.constants import SP_TZ
    from rentivo.jobs.handlers.communication import handle_communication_send

    comm = _seed_comm(engine)
    with engine.connect() as c:
        SQLAlchemyCommunicationRepository(c, Base64Backend()).mark_sent(comm.id, datetime(2026, 6, 12, tzinfo=SP_TZ))

    sent = {}

    class BoomBackend:
        def send(self, message):  # pragma: no cover - must never be called
            sent["called"] = True
            return "msg"

    monkeypatch.setattr(mod, "get_engine", lambda: engine)
    monkeypatch.setattr(mod, "get_encryption", lambda: Base64Backend())
    monkeypatch.setattr(mod, "get_email_backend", lambda: BoomBackend())

    handle_communication_send({"communication_id": comm.id})

    assert "called" not in sent
    with engine.connect() as c:
        assert SQLAlchemyCommunicationRepository(c, Base64Backend()).get_by_id(comm.id).status == "sent"


def test_handler_permanent_error_when_pdf_object_missing(engine, monkeypatch):
    """A key present in the DB but absent in storage fails permanently, not retried."""
    import rentivo.jobs.handlers.communication as mod
    from rentivo.jobs.handlers.communication import handle_communication_send

    comm = _seed_comm(engine)

    class MissingStorage:
        def get(self, key):
            raise FileNotFoundError(key)

    monkeypatch.setattr(mod, "get_engine", lambda: engine)
    monkeypatch.setattr(mod, "get_encryption", lambda: Base64Backend())
    monkeypatch.setattr(mod, "get_storage", lambda: MissingStorage())
    with pytest.raises(PermanentJobError):
        handle_communication_send({"communication_id": comm.id})


def test_fail_hook_marks_failed(engine, monkeypatch):
    import rentivo.jobs.handlers.communication as mod
    from rentivo.jobs.handlers.communication import _on_communication_send_failed

    comm = _seed_comm(engine)
    monkeypatch.setattr(mod, "get_engine", lambda: engine)
    monkeypatch.setattr(mod, "get_encryption", lambda: Base64Backend())
    _on_communication_send_failed({"communication_id": comm.id})
    with engine.connect() as c:
        repo = SQLAlchemyCommunicationRepository(c, Base64Backend())
        assert repo.get_by_id(comm.id).status == "failed"


def test_fail_hook_does_not_overwrite_sent(engine, monkeypatch):
    """A late dead-letter must not flip a delivered row back to 'failed'."""
    from datetime import datetime

    import rentivo.jobs.handlers.communication as mod
    from rentivo.constants import SP_TZ
    from rentivo.jobs.handlers.communication import _on_communication_send_failed

    comm = _seed_comm(engine)
    with engine.connect() as c:
        SQLAlchemyCommunicationRepository(c, Base64Backend()).mark_sent(comm.id, datetime(2026, 6, 12, tzinfo=SP_TZ))

    monkeypatch.setattr(mod, "get_engine", lambda: engine)
    monkeypatch.setattr(mod, "get_encryption", lambda: Base64Backend())
    _on_communication_send_failed({"communication_id": comm.id})
    with engine.connect() as c:
        assert SQLAlchemyCommunicationRepository(c, Base64Backend()).get_by_id(comm.id).status == "sent"
