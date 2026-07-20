from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from rentivo.api.app import create_app
from rentivo.settings import settings
from tests.conftest import SCHEMA_DDL

_API_KEY_SCHEMA = (
    """
    CREATE TABLE api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid VARCHAR(26) NOT NULL,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name VARCHAR(255) NOT NULL,
        secret_hash BINARY(32) NOT NULL,
        key_start VARCHAR(4) NOT NULL,
        key_end VARCHAR(2) NOT NULL,
        is_login_token BOOLEAN NOT NULL DEFAULT 0,
        expires_at DATETIME NOT NULL,
        last_used_at DATETIME,
        created_at DATETIME NOT NULL,
        revoked_at DATETIME
    )
    """,
    "CREATE UNIQUE INDEX ix_api_keys_uuid ON api_keys (uuid)",
    "CREATE UNIQUE INDEX ix_api_keys_secret_hash ON api_keys (secret_hash)",
    "CREATE INDEX ix_api_keys_user_id ON api_keys (user_id)",
    "CREATE INDEX ix_api_keys_expires_at ON api_keys (expires_at)",
    "CREATE INDEX ix_api_keys_revoked_at ON api_keys (revoked_at)",
    """
    CREATE TABLE api_key_scopes (
        api_key_id INTEGER NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
        scope VARCHAR(64) NOT NULL,
        PRIMARY KEY (api_key_id, scope)
    )
    """,
    """
    CREATE TABLE api_key_resource_grants (
        api_key_id INTEGER NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
        resource_type VARCHAR(20) NOT NULL,
        resource_id INTEGER NOT NULL,
        CHECK (resource_type IN ('user', 'organization')),
        PRIMARY KEY (api_key_id, resource_type, resource_id)
    )
    """,
)


def _create_schema(engine) -> None:
    with engine.begin() as connection:
        for statement in SCHEMA_DDL.strip().split(";"):
            if statement.strip():
                connection.execute(text(statement))
        for statement in _API_KEY_SCHEMA:
            connection.execute(text(statement))


def test_native_signup_bearer_session_and_logout_persist_the_login_lifecycle(
    monkeypatch,
    tmp_path,
    fake_encryption,
) -> None:
    import rentivo.api.app as api_app

    engine = create_engine(f"sqlite:///{tmp_path / 'native-auth.db'}")
    _create_schema(engine)
    monkeypatch.setattr(api_app, "get_engine", lambda: engine)
    monkeypatch.setattr(api_app, "get_encryption", lambda: fake_encryption)
    monkeypatch.setattr(settings, "api_key_login_ttl_seconds", 24 * 60 * 60)

    before_signup = datetime.now(UTC)
    with TestClient(create_app()) as client:
        signup = client.post(
            "/api/v1/auth/signup",
            json={
                "email": "native@example.com",
                "password": "correct horse battery staple",
                "confirm_password": "correct horse battery staple",
                "turnstile_token": "",
                "credential_transport": "body",
            },
        )
        after_signup = datetime.now(UTC)

        assert signup.status_code == 200
        credential = signup.json()["access_token"]
        assert credential.startswith("rntv-v1-")
        assert settings.access_cookie_name not in signup.cookies
        assert settings.csrf_cookie_name not in signup.cookies

        with engine.connect() as connection:
            key = (
                connection.execute(text("SELECT id, uuid, user_id, is_login_token, expires_at FROM api_keys"))
                .mappings()
                .one()
            )
        expires_at = datetime.fromisoformat(str(key["expires_at"])).replace(tzinfo=UTC)
        assert key["is_login_token"] == 1
        assert before_signup + timedelta(days=1) <= expires_at <= after_signup + timedelta(days=1)

        authorization = {"Authorization": f"Bearer {credential}"}
        session = client.get("/api/v1/auth/session", headers=authorization)
        assert session.status_code == 200
        assert session.json()["bootstrap"]["user"]["email"] == "native@example.com"

        logout = client.post("/api/v1/auth/logout", headers=authorization)
        assert logout.status_code == 204

        revoked_session = client.get("/api/v1/auth/session", headers=authorization)
        assert revoked_session.status_code == 401

    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM api_keys")).scalar_one() == 0
        user = (
            connection.execute(
                text("SELECT id, email_hash FROM users WHERE id = :user_id"),
                {"user_id": key["user_id"]},
            )
            .mappings()
            .one()
        )
    assert user["email_hash"]
    engine.dispose()
