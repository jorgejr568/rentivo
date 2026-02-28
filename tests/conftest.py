"""Root conftest — in-memory SQLite engine and fixtures for the full schema."""

from __future__ import annotations

import pytest
from sqlalchemy import Connection, create_engine, event, text
from sqlalchemy.engine import Engine

from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import Billing, BillingItem, ItemType

# Matches Alembic head: a7b8c9d0e1f2 (replace UUID4 with ULID)
SCHEMA_DDL = """
CREATE TABLE billings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    pix_key TEXT NOT NULL DEFAULT '',
    uuid VARCHAR(26) NOT NULL UNIQUE,
    owner_type TEXT NOT NULL DEFAULT 'user',
    owner_id INTEGER NOT NULL DEFAULT 0,
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
    email TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid VARCHAR(26) NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    enforce_mfa TINYINT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    deleted_at DATETIME
);

CREATE TABLE organization_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    UNIQUE(organization_id, user_id)
);

CREATE TABLE invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid VARCHAR(26) NOT NULL UNIQUE,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    invited_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    invited_by_user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL,
    responded_at DATETIME
);

CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid VARCHAR(26) NOT NULL UNIQUE,
    event_type VARCHAR(50) NOT NULL,
    actor_id INTEGER,
    actor_username VARCHAR(255) NOT NULL DEFAULT '',
    source VARCHAR(10) NOT NULL,
    entity_type VARCHAR(50) NOT NULL DEFAULT '',
    entity_id INTEGER,
    entity_uuid VARCHAR(26) NOT NULL DEFAULT '',
    previous_state TEXT,
    new_state TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at DATETIME NOT NULL
);

CREATE TABLE receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid VARCHAR(26) NOT NULL UNIQUE,
    bill_id INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    content_type TEXT NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL
);

CREATE TABLE user_totp (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    secret TEXT NOT NULL,
    confirmed TINYINT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    confirmed_at DATETIME
);

CREATE TABLE user_recovery_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL,
    used_at DATETIME,
    created_at DATETIME NOT NULL
);

CREATE TABLE user_passkeys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid VARCHAR(26) NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    credential_id TEXT NOT NULL,
    public_key TEXT NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0,
    name VARCHAR(255) NOT NULL DEFAULT '',
    transports TEXT,
    created_at DATETIME NOT NULL,
    last_used_at DATETIME
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
