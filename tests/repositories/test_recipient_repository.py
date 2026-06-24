from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from rentivo.encryption.base64 import Base64Backend
from rentivo.models.recipient import Recipient
from rentivo.repositories.sqlalchemy.recipient import SQLAlchemyRecipientRepository
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
    return SQLAlchemyRecipientRepository(conn, Base64Backend())


def test_replace_and_list_round_trips(conn):
    repo = _repo(conn)
    repo.replace_for_billing(
        1,
        [
            Recipient(billing_id=1, name="João", email="joao@example.com"),
            Recipient(billing_id=1, name="Ana", email="ana@example.com"),
        ],
    )
    rows = repo.list_by_billing(1)
    assert [r.name for r in rows] == ["João", "Ana"]
    assert [r.email for r in rows] == ["joao@example.com", "ana@example.com"]
    assert [r.sort_order for r in rows] == [0, 1]


def test_values_are_encrypted_at_rest(conn):
    repo = _repo(conn)
    repo.replace_for_billing(1, [Recipient(billing_id=1, name="João", email="joao@example.com")])
    raw = conn.execute(text("SELECT name, email FROM billing_recipients")).fetchone()
    assert raw[0].startswith("b64:v1:")
    assert raw[1].startswith("b64:v1:")


def test_phone_round_trips_and_is_encrypted(conn):
    repo = _repo(conn)
    repo.replace_for_billing(
        1, [Recipient(billing_id=1, name="João", email="joao@example.com", phone="+5511999998888")]
    )
    assert repo.list_by_billing(1)[0].phone == "+5511999998888"
    raw = conn.execute(text("SELECT phone FROM billing_recipients")).scalar()
    assert raw.startswith("b64:v1:")


def test_missing_phone_stored_as_null_and_read_as_none(conn):
    repo = _repo(conn)
    repo.replace_for_billing(1, [Recipient(billing_id=1, name="João", email="joao@example.com")])
    assert repo.list_by_billing(1)[0].phone is None
    assert conn.execute(text("SELECT phone FROM billing_recipients")).scalar() is None


def test_list_empty_returns_empty(conn):
    repo = _repo(conn)
    assert repo.list_by_billing(999) == []


def test_replace_overwrites_previous_set(conn):
    repo = _repo(conn)
    repo.replace_for_billing(1, [Recipient(billing_id=1, name="Old", email="old@x.com")])
    repo.replace_for_billing(1, [Recipient(billing_id=1, name="New", email="new@x.com")])
    rows = repo.list_by_billing(1)
    assert [r.name for r in rows] == ["New"]


def test_get_by_uuid(conn):
    repo = _repo(conn)
    repo.replace_for_billing(1, [Recipient(billing_id=1, name="João", email="joao@example.com")])
    created = repo.list_by_billing(1)[0]
    fetched = repo.get_by_uuid(created.uuid)
    assert fetched is not None
    assert fetched.name == "João"
    assert repo.get_by_uuid("nonexistent") is None
