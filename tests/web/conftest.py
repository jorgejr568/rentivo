"""Web test fixtures — TestClient with shared in-memory SQLite."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

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
    from landlord.repositories.sqlalchemy import SQLAlchemyUserRepository
    from landlord.services.user_service import UserService

    with test_engine.connect() as conn:
        user_repo = SQLAlchemyUserRepository(conn)
        user_service = UserService(user_repo)
        user_service.create_user("testuser", "testpass")

    client.post("/login", data={"username": "testuser", "password": "testpass"})
    return client
