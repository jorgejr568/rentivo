"""Web test fixtures — TestClient with shared in-memory SQLite."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from rentivo.models.billing import Billing, BillingItem, ItemType
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyUserRepository,
)
from rentivo.services.bill_service import BillService
from rentivo.storage.local import LocalStorage
from tests.conftest import SCHEMA_DDL


def _make_test_engine():
    """Create a fresh in-memory SQLite engine with shared connection pool."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    with engine.connect() as conn:
        for statement in SCHEMA_DDL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()

    return engine


def get_test_user_id(engine):
    """Get the ID of the test user."""
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id FROM users WHERE username = 'testuser'")).fetchone()
        return row[0] if row else 1


def create_billing_in_db(engine, **overrides):
    """Create a billing in the test DB. Shared helper for web route tests."""
    if "owner_id" not in overrides:
        overrides.setdefault("owner_id", get_test_user_id(engine))
    overrides.setdefault("owner_type", "user")
    defaults = dict(
        name="Apt 101",
        description="",
        pix_key="",
        items=[
            BillingItem(description="Aluguel", amount=285000, item_type=ItemType.FIXED),
            BillingItem(description="Água", amount=0, item_type=ItemType.VARIABLE),
        ],
    )
    defaults.update(overrides)
    with engine.connect() as conn:
        repo = SQLAlchemyBillingRepository(conn)
        billing = repo.create(Billing(**defaults))
    return billing


def generate_bill_in_db(engine, billing, tmp_path):
    """Generate a bill in the test DB. Shared helper for web route tests."""
    with engine.connect() as conn:
        bill_repo = SQLAlchemyBillRepository(conn)
        storage = LocalStorage(str(tmp_path))
        service = BillService(bill_repo, storage)
        bill = service.generate_bill(
            billing=billing,
            reference_month="2025-03",
            variable_amounts={},
            extras=[],
            notes="note",
            due_date="10/04/2025",
        )
    return bill


def create_org_in_db(engine, name, created_by_user_id):
    """Create an organization in the test DB."""
    from rentivo.services.organization_service import OrganizationService

    with engine.connect() as conn:
        repo = SQLAlchemyOrganizationRepository(conn)
        service = OrganizationService(repo)
        org = service.create_organization(name, created_by_user_id)
    return org


def get_audit_logs(engine, event_type=None):
    """Query audit_logs from the test DB. Optionally filter by event_type."""
    from rentivo.repositories.sqlalchemy import SQLAlchemyAuditLogRepository

    with engine.connect() as conn:
        repo = SQLAlchemyAuditLogRepository(conn)
        logs = repo.list_recent(limit=100)
        if event_type:
            logs = [log for log in logs if log.event_type == event_type]
        return logs


def get_csrf_token(client) -> str:
    """Extract the CSRF token from a page that renders a form."""
    response = client.get("/security")
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    if match:
        return match.group(1)
    return ""


@pytest.fixture(autouse=True)
def web_test_db(monkeypatch):
    """Set up in-memory DB and patch the web app to use it."""
    engine = _make_test_engine()

    import web.deps as deps_module

    monkeypatch.setattr(deps_module, "get_engine", lambda: engine)

    import web.app as app_module

    monkeypatch.setattr(app_module, "initialize_db", lambda: None)

    yield engine

    engine.dispose()


@pytest.fixture()
def test_engine(web_test_db):
    """Expose the test engine for helpers that need direct DB access."""
    return web_test_db


@pytest.fixture()
def client():
    from starlette.testclient import TestClient

    from web.app import app

    return TestClient(app)


@pytest.fixture()
def auth_client(client, test_engine):
    """Client that is already logged in."""
    with test_engine.connect() as conn:
        user_repo = SQLAlchemyUserRepository(conn)
        from rentivo.services.user_service import UserService

        user_service = UserService(user_repo)
        user_service.create_user("testuser", "testpass")

    client.post("/login", data={"username": "testuser", "password": "testpass"})
    return client


@pytest.fixture()
def csrf_token(auth_client) -> str:
    """Get a valid CSRF token for the authenticated client."""
    return get_csrf_token(auth_client)
