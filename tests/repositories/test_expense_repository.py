import inspect

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from rentivo.encryption.base64 import Base64Backend
from rentivo.models.billing import Billing, BillingItem, ItemType
from rentivo.models.expense import Expense
from rentivo.repositories.base import ExpenseRepository
from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository
from rentivo.repositories.sqlalchemy.expense import SQLAlchemyExpenseRepository
from tests.conftest import SCHEMA_DDL


def test_expense_repository_is_abstract():
    assert inspect.isabstract(ExpenseRepository)
    methods = set(ExpenseRepository.__abstractmethods__)
    assert methods == {"create", "get_by_uuid", "list_by_billing", "delete", "total_for_billings"}


@pytest.fixture
def conn():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    with engine.connect() as c:
        for stmt in SCHEMA_DDL.strip().split(";"):
            if stmt.strip():
                c.execute(text(stmt))
        c.commit()
    connection = engine.connect()
    yield connection
    connection.close()
    engine.dispose()


@pytest.fixture
def billing(conn):
    repo = SQLAlchemyBillingRepository(conn, Base64Backend())
    return repo.create(
        Billing(
            name="Apt 101",
            items=[BillingItem(description="Aluguel", amount=285000, item_type=ItemType.FIXED)],
            owner_type="user",
            owner_id=1,
        )
    )


def test_create_encrypts_description_and_roundtrips(conn, billing):
    repo = SQLAlchemyExpenseRepository(conn, Base64Backend())
    created = repo.create(
        Expense(billing_id=billing.id, description="IPTU 2026", amount=12000, category="iptu", incurred_on="2026-01-10")
    )
    assert created.id is not None
    assert created.uuid != ""
    # stored ciphertext is NOT the plaintext
    raw = conn.execute(text("SELECT description FROM expenses WHERE id = :i"), {"i": created.id}).scalar_one()
    assert raw.startswith("b64:v1:")
    # read back decrypts
    fetched = repo.get_by_uuid(created.uuid)
    assert fetched.description == "IPTU 2026"
    assert fetched.amount == 12000
    assert fetched.category == "iptu"
    assert fetched.incurred_on == "2026-01-10"


def test_list_by_billing_orders_and_batch_decrypts(conn, billing):
    repo = SQLAlchemyExpenseRepository(conn, Base64Backend())
    repo.create(Expense(billing_id=billing.id, description="A", amount=100, category="iptu", incurred_on="2026-01-01"))
    repo.create(
        Expense(billing_id=billing.id, description="B", amount=200, category="outros", incurred_on="2026-02-01")
    )
    rows = repo.list_by_billing(billing.id)
    assert [e.description for e in rows] == ["B", "A"]  # newest incurred_on first


def test_get_by_uuid_missing_returns_none(conn):
    repo = SQLAlchemyExpenseRepository(conn, Base64Backend())
    assert repo.get_by_uuid("01BX5ZZKBKACTAV9WEVGEMMVRZ") is None


def test_delete_soft_deletes(conn, billing):
    repo = SQLAlchemyExpenseRepository(conn, Base64Backend())
    e = repo.create(
        Expense(billing_id=billing.id, description="X", amount=500, category="seguro", incurred_on="2026-03-01")
    )
    repo.delete(e.id)
    assert repo.get_by_uuid(e.uuid) is None
    assert repo.list_by_billing(billing.id) == []
    deleted_at = conn.execute(text("SELECT deleted_at FROM expenses WHERE id = :i"), {"i": e.id}).scalar_one()
    assert deleted_at is not None


def test_total_for_billings(conn, billing):
    repo = SQLAlchemyExpenseRepository(conn, Base64Backend())
    repo.create(Expense(billing_id=billing.id, description="A", amount=100, category="iptu", incurred_on="2026-01-01"))
    e2 = repo.create(
        Expense(billing_id=billing.id, description="B", amount=250, category="outros", incurred_on="2026-02-01")
    )
    repo.delete(e2.id)  # excluded
    assert repo.total_for_billings([billing.id]) == 100
    assert repo.total_for_billings([]) == 0
    assert repo.total_for_billings([999999]) == 0


def test_factory_builds_expense_repository(conn, monkeypatch):
    import rentivo.repositories.factory as factory

    monkeypatch.setattr(factory, "_connection", lambda: conn)
    monkeypatch.setattr(factory, "_encryption", lambda: Base64Backend())
    repo = factory.get_expense_repository()
    assert isinstance(repo, SQLAlchemyExpenseRepository)
