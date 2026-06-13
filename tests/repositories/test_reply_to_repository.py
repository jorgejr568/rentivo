from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from rentivo.encryption.base64 import Base64Backend
from rentivo.models.recipient import Recipient
from rentivo.repositories.sqlalchemy.reply_to import SQLAlchemyReplyToRecipientRepository
from tests.conftest import SCHEMA_DDL


@pytest.fixture()
def conn():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.connect() as c:
        for stmt in SCHEMA_DDL.strip().split(";"):
            if stmt.strip():
                c.execute(text(stmt))
        c.commit()
        yield c


def _repo(conn):
    return SQLAlchemyReplyToRecipientRepository(conn, Base64Backend())


def test_replace_and_list_round_trips(conn):
    repo = _repo(conn)
    repo.replace_for_billing(
        1,
        [
            Recipient(billing_id=1, name="Ana", email="ana@example.com"),
            Recipient(billing_id=1, name="Bruno", email="bruno@example.com"),
        ],
    )
    rows = repo.list_by_billing(1)
    assert [(r.name, r.email) for r in rows] == [("Ana", "ana@example.com"), ("Bruno", "bruno@example.com")]
    assert [r.sort_order for r in rows] == [0, 1]


def test_values_are_encrypted_at_rest(conn):
    repo = _repo(conn)
    repo.replace_for_billing(1, [Recipient(billing_id=1, name="Ana", email="ana@example.com")])
    raw = conn.execute(text("SELECT name, email FROM billing_reply_to")).fetchone()
    assert raw[0].startswith("b64:v1:") and raw[1].startswith("b64:v1:")


def test_replace_overwrites_previous_set(conn):
    repo = _repo(conn)
    repo.replace_for_billing(1, [Recipient(billing_id=1, name="Old", email="old@x.com")])
    repo.replace_for_billing(1, [Recipient(billing_id=1, name="New", email="new@x.com")])
    assert [r.name for r in repo.list_by_billing(1)] == ["New"]


def test_list_empty_returns_empty(conn):
    assert _repo(conn).list_by_billing(999) == []


def test_get_by_uuid(conn):
    repo = _repo(conn)
    repo.replace_for_billing(1, [Recipient(billing_id=1, name="Ana", email="ana@example.com")])
    created = repo.list_by_billing(1)[0]
    assert repo.get_by_uuid(created.uuid).name == "Ana"
    assert repo.get_by_uuid("missing") is None
