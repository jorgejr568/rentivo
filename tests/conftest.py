"""Root conftest — in-memory SQLite engine and fixtures for the full schema."""
from __future__ import annotations

import pytest
from sqlalchemy import Connection, create_engine, event, text
from sqlalchemy.engine import Engine

from landlord.models.bill import Bill, BillLineItem
from landlord.models.billing import Billing, BillingItem, ItemType


# Matches Alembic head: e5f6a7b8c9d0 (add paid_at to bills)
SCHEMA_DDL = """
CREATE TABLE billings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    pix_key TEXT NOT NULL DEFAULT '',
    uuid VARCHAR(26) NOT NULL UNIQUE,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    deleted_at DATETIME
);

CREATE TABLE billing_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    billing_id INTEGER NOT NULL REFERENCES billings(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    amount INTEGER NOT NULL DEFAULT 0,
    item_type TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    billing_id INTEGER NOT NULL REFERENCES billings(id),
    reference_month TEXT NOT NULL,
    total_amount INTEGER NOT NULL DEFAULT 0,
    pdf_path TEXT,
    notes TEXT NOT NULL DEFAULT '',
    uuid VARCHAR(26) NOT NULL UNIQUE,
    due_date TEXT,
    created_at DATETIME NOT NULL,
    paid_at DATETIME,
    deleted_at DATETIME
);

CREATE TABLE bill_line_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    amount INTEGER NOT NULL,
    item_type TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


@pytest.fixture()
def db_engine() -> Engine:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


@pytest.fixture()
def db_connection(db_engine: Engine) -> Connection:
    conn = db_engine.connect()
    for statement in SCHEMA_DDL.strip().split(";"):
        stmt = statement.strip()
        if stmt:
            conn.execute(text(stmt))
    conn.commit()
    yield conn
    conn.close()


def _sample_billing(**overrides) -> Billing:
    defaults = dict(
        name="Apt 101",
        description="Monthly rent",
        pix_key="test@pix.com",
        items=[
            BillingItem(
                description="Aluguel",
                amount=285000,
                item_type=ItemType.FIXED,
                sort_order=0,
            ),
            BillingItem(
                description="Água",
                amount=0,
                item_type=ItemType.VARIABLE,
                sort_order=1,
            ),
        ],
    )
    defaults.update(overrides)
    return Billing(**defaults)


def _sample_bill(billing_id: int = 1, **overrides) -> Bill:
    defaults = dict(
        billing_id=billing_id,
        reference_month="2025-03",
        total_amount=295000,
        line_items=[
            BillLineItem(
                description="Aluguel",
                amount=285000,
                item_type=ItemType.FIXED,
                sort_order=0,
            ),
            BillLineItem(
                description="Água",
                amount=10000,
                item_type=ItemType.VARIABLE,
                sort_order=1,
            ),
        ],
        notes="Test note",
        due_date="10/04/2025",
    )
    defaults.update(overrides)
    return Bill(**defaults)


@pytest.fixture()
def sample_billing():
    return _sample_billing


@pytest.fixture()
def sample_bill():
    return _sample_bill
