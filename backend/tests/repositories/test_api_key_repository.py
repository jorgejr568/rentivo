from __future__ import annotations

import traceback
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import Connection, text
from sqlalchemy.exc import SQLAlchemyError

from rentivo.models import APIKey, APIKeyGrant
from rentivo.models.user import User
from rentivo.observability import instrument_sqlalchemy, span, tracing
from rentivo.repositories.base import APIKeyPersistenceError
from rentivo.repositories.sqlalchemy import SQLAlchemyAPIKeyRepository, SQLAlchemyUserRepository


@pytest.fixture()
def api_key_repo(db_connection: Connection) -> SQLAlchemyAPIKeyRepository:
    statements = (
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
            CONSTRAINT ck_api_key_grant_resource_type
                CHECK (resource_type IN ('user', 'organization')),
            PRIMARY KEY (api_key_id, resource_type, resource_id)
        )
        """,
    )
    for statement in statements:
        db_connection.execute(text(statement))
    db_connection.commit()
    return SQLAlchemyAPIKeyRepository(db_connection)


@pytest.fixture()
def key_owner(user_repo: SQLAlchemyUserRepository) -> User:
    return user_repo.create(User(email="api-key-owner@example.com", password_hash="x"))


def make_key(user_id: int, **overrides: object) -> APIKey:
    defaults: dict[str, object] = {
        "uuid": "01K0APIKEY0000000000000000",
        "user_id": user_id,
        "name": "Accounting export",
        "secret_hash": b"i" * 32,
        "key_start": "aBcD",
        "key_end": "yZ",
        "expires_at": datetime(2026, 10, 15, 12, 30, 45, 123456, tzinfo=UTC),
    }
    defaults.update(overrides)
    return APIKey(**defaults)


def test_repository_round_trips_scopes_and_grants(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
) -> None:
    integration_key = make_key(key_owner.id)

    saved = api_key_repo.create(
        integration_key,
        scopes=frozenset({"profile:read", "billings:read"}),
        grants=(APIKeyGrant(resource_type="user", resource_id=key_owner.id),),
    )
    loaded = api_key_repo.get_by_secret_hash(integration_key.secret_hash)

    assert loaded == saved
    assert loaded.scopes == frozenset({"profile:read", "billings:read"})
    assert loaded.grants == (APIKeyGrant(resource_type="user", resource_id=key_owner.id),)
    assert loaded.id is not None
    assert loaded.created_at is not None
    assert loaded.created_at.tzinfo is UTC
    assert loaded.expires_at == integration_key.expires_at


def test_repository_treats_naive_storage_inputs_as_utc(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
) -> None:
    naive_expiry = datetime(2026, 10, 15, 12, 30, 45, 123456)

    saved = api_key_repo.create(
        make_key(key_owner.id, expires_at=naive_expiry),
        scopes=frozenset(),
        grants=(),
    )

    assert saved.expires_at == naive_expiry.replace(tzinfo=UTC)


def test_list_integration_keys_never_returns_login_tokens(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
) -> None:
    login_key = make_key(
        key_owner.id,
        uuid="01K0LOGIN00000000000000000",
        secret_hash=b"l" * 32,
        name="Web login",
        is_login_token=True,
    )
    integration_key = make_key(key_owner.id)
    api_key_repo.create(login_key, scopes=frozenset(), grants=())
    api_key_repo.create(integration_key, scopes=frozenset(), grants=())

    assert [key.uuid for key in api_key_repo.list_integrations(key_owner.id)] == [integration_key.uuid]


def test_integration_lookup_requires_matching_owner_and_excludes_login_tokens(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
) -> None:
    integration = api_key_repo.create(make_key(key_owner.id), scopes=frozenset(), grants=())
    login = api_key_repo.create(
        make_key(
            key_owner.id,
            uuid="01K0LOGIN00000000000000000",
            secret_hash=b"l" * 32,
            is_login_token=True,
        ),
        scopes=frozenset(),
        grants=(),
    )

    assert api_key_repo.get_integration_by_uuid(key_owner.id, integration.uuid) == integration
    assert api_key_repo.get_integration_by_uuid(key_owner.id + 1, integration.uuid) is None
    assert api_key_repo.get_integration_by_uuid(key_owner.id, login.uuid) is None
    assert api_key_repo.get_by_secret_hash(b"missing" * 4) is None


def test_update_integration_replaces_mutable_aggregate_fields(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
) -> None:
    created = api_key_repo.create(
        make_key(key_owner.id),
        scopes=frozenset({"profile:read"}),
        grants=(APIKeyGrant(resource_type="user", resource_id=key_owner.id),),
    )

    updated = api_key_repo.update_integration(
        created.model_copy(update={"id": None, "name": "New export name"}),
        scopes=frozenset({"billings:read"}),
        grants=(APIKeyGrant(resource_type="organization", resource_id=42),),
    )

    assert updated.name == "New export name"
    assert updated.scopes == frozenset({"billings:read"})
    assert updated.grants == (APIKeyGrant(resource_type="organization", resource_id=42),)
    assert updated.secret_hash == created.secret_hash
    assert updated.expires_at == created.expires_at


def test_create_rolls_back_entire_aggregate_on_child_failure(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
) -> None:
    key = make_key(key_owner.id)
    duplicate_grant = APIKeyGrant(resource_type="user", resource_id=key_owner.id)

    with pytest.raises(APIKeyPersistenceError):
        api_key_repo.create(key, scopes=frozenset(), grants=(duplicate_grant, duplicate_grant))

    assert api_key_repo.get_by_secret_hash(key.secret_hash) is None


def test_create_rolls_back_and_reraises_non_database_failure(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
    monkeypatch,
) -> None:
    key = make_key(key_owner.id)
    monkeypatch.setattr(api_key_repo, "_insert_children", MagicMock(side_effect=RuntimeError("child failure")))

    with pytest.raises(RuntimeError, match="child failure"):
        api_key_repo.create(key, scopes=frozenset(), grants=())

    assert api_key_repo.get_by_secret_hash(key.secret_hash) is None


def test_hash_lookup_sanitizes_database_failures() -> None:
    connection = MagicMock()
    connection.execute.side_effect = SQLAlchemyError("S" * 32)
    repository = SQLAlchemyAPIKeyRepository(connection)

    with pytest.raises(APIKeyPersistenceError) as exc_info:
        repository.get_by_secret_hash(b"S" * 32)

    assert "S" * 32 not in "".join(traceback.format_exception(exc_info.value))
    assert exc_info.value.__context__ is None
    connection.rollback.assert_called_once_with()


def test_duplicate_hash_never_reaches_trace_details(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
) -> None:
    secret_hash = b"S" * 32
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracing._reset_for_tests()
    tracing.configure_tracing(provider=provider)
    instrument_sqlalchemy(api_key_repo.conn.engine)
    try:
        api_key_repo.create(
            make_key(key_owner.id, secret_hash=secret_hash),
            scopes=frozenset(),
            grants=(),
        )
        exporter.clear()

        with pytest.raises(APIKeyPersistenceError) as exc_info:
            with span("HTTP POST"):
                api_key_repo.create(
                    make_key(
                        key_owner.id,
                        uuid="01K0DUPLICATE0000000000000",
                        secret_hash=secret_hash,
                    ),
                    scopes=frozenset(),
                    grants=(),
                )

        serialized_spans = repr(
            [
                (span.status.description, [(event.name, dict(event.attributes)) for event in span.events])
                for span in exporter.get_finished_spans()
            ]
        )
        assert all(span.attributes.get("db.system") is None for span in exporter.get_finished_spans())
        assert "S" * 32 not in serialized_spans
        assert secret_hash.hex() not in serialized_spans
        formatted_exception = "".join(traceback.format_exception(exc_info.value))
        assert "S" * 32 not in formatted_exception
        assert secret_hash.hex() not in formatted_exception
        assert exc_info.value.__context__ is None
    finally:
        SQLAlchemyInstrumentor().uninstrument()
        tracing._reset_for_tests()


def test_update_rolls_back_entire_aggregate_on_child_failure(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
) -> None:
    original_grant = APIKeyGrant(resource_type="user", resource_id=key_owner.id)
    created = api_key_repo.create(
        make_key(key_owner.id),
        scopes=frozenset({"profile:read"}),
        grants=(original_grant,),
    )

    with pytest.raises(APIKeyPersistenceError):
        api_key_repo.update_integration(
            created.model_copy(update={"name": "Must roll back"}),
            scopes=frozenset({"billings:read"}),
            grants=(original_grant, original_grant),
        )

    loaded = api_key_repo.get_by_secret_hash(created.secret_hash)
    assert loaded is not None
    assert loaded.name == created.name
    assert loaded.scopes == frozenset({"profile:read"})
    assert loaded.grants == (original_grant,)


def test_update_rolls_back_and_reraises_non_database_failure(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
    monkeypatch,
) -> None:
    created = api_key_repo.create(make_key(key_owner.id), scopes=frozenset(), grants=())
    monkeypatch.setattr(api_key_repo, "_insert_children", MagicMock(side_effect=RuntimeError("child failure")))

    with pytest.raises(RuntimeError, match="child failure"):
        api_key_repo.update_integration(
            created.model_copy(update={"name": "Must roll back"}),
            scopes=frozenset({"profile:read"}),
            grants=(),
        )

    loaded = api_key_repo.get_by_secret_hash(created.secret_hash)
    assert loaded is not None
    assert loaded.name == created.name


def test_update_integration_rejects_login_token_and_unknown_key(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
) -> None:
    login = api_key_repo.create(
        make_key(key_owner.id, is_login_token=True),
        scopes=frozenset(),
        grants=(),
    )

    assert api_key_repo.update_integration(login, scopes=frozenset(), grants=()) is None
    assert (
        api_key_repo.update_integration(
            make_key(key_owner.id, uuid="01K0MISSING000000000000000"),
            scopes=frozenset(),
            grants=(),
        )
        is None
    )


def test_delete_login_token_only_deletes_login_tokens(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
) -> None:
    integration = api_key_repo.create(make_key(key_owner.id), scopes=frozenset(), grants=())
    login = api_key_repo.create(
        make_key(
            key_owner.id,
            uuid="01K0LOGIN00000000000000000",
            secret_hash=b"l" * 32,
            is_login_token=True,
        ),
        scopes=frozenset({"profile:read"}),
        grants=(),
    )

    assert api_key_repo.delete_login_token(integration.id) is False
    assert api_key_repo.delete_login_token(login.id) is True
    assert api_key_repo.get_by_secret_hash(login.secret_hash) is None
    assert api_key_repo.get_by_secret_hash(integration.secret_hash) is not None


def test_revoke_integration_is_owner_scoped_and_idempotent(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
) -> None:
    integration = api_key_repo.create(make_key(key_owner.id), scopes=frozenset(), grants=())
    revoked_at = datetime(2026, 7, 17, 15, 1, 2, 654321, tzinfo=UTC)

    assert api_key_repo.revoke_integration(key_owner.id + 1, integration.uuid, revoked_at) is False
    assert api_key_repo.revoke_integration(key_owner.id, integration.uuid, revoked_at) is True
    assert api_key_repo.revoke_integration(key_owner.id, integration.uuid, revoked_at + timedelta(seconds=1)) is True
    loaded = api_key_repo.get_by_secret_hash(integration.secret_hash)
    assert loaded is not None
    assert loaded.revoked_at == revoked_at


def test_revoke_all_login_tokens_leaves_integrations_active(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
) -> None:
    login = api_key_repo.create(make_key(key_owner.id, is_login_token=True), scopes=frozenset(), grants=())
    integration = api_key_repo.create(
        make_key(
            key_owner.id,
            uuid="01K0INTEGRATION00000000000",
            secret_hash=b"j" * 32,
        ),
        scopes=frozenset(),
        grants=(),
    )

    assert api_key_repo.revoke_all_login_tokens(key_owner.id) == 1
    assert api_key_repo.get_by_secret_hash(login.secret_hash) is None
    assert api_key_repo.get_by_secret_hash(integration.secret_hash) is not None


def test_delete_expired_login_tokens_uses_cutoff_and_leaves_integrations(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
) -> None:
    cutoff = datetime(2026, 7, 17, 12, tzinfo=UTC)
    expired_login = api_key_repo.create(
        make_key(key_owner.id, is_login_token=True, expires_at=cutoff - timedelta(microseconds=1)),
        scopes=frozenset(),
        grants=(),
    )
    live_login = api_key_repo.create(
        make_key(
            key_owner.id,
            uuid="01K0LOGINLIVE0000000000000",
            secret_hash=b"l" * 32,
            is_login_token=True,
            expires_at=cutoff + timedelta(microseconds=1),
        ),
        scopes=frozenset(),
        grants=(),
    )
    boundary_login = api_key_repo.create(
        make_key(
            key_owner.id,
            uuid="01K0LOGINBOUNDARY000000000",
            secret_hash=b"b" * 32,
            is_login_token=True,
            expires_at=cutoff,
        ),
        scopes=frozenset(),
        grants=(),
    )
    expired_integration = api_key_repo.create(
        make_key(
            key_owner.id,
            uuid="01K0EXPIREDINT000000000000",
            secret_hash=b"e" * 32,
            expires_at=cutoff - timedelta(days=1),
        ),
        scopes=frozenset(),
        grants=(),
    )

    assert api_key_repo.delete_expired_login_tokens(cutoff) == 2
    assert api_key_repo.get_by_secret_hash(expired_login.secret_hash) is None
    assert api_key_repo.get_by_secret_hash(boundary_login.secret_hash) is None
    assert api_key_repo.get_by_secret_hash(live_login.secret_hash) is not None
    assert api_key_repo.get_by_secret_hash(expired_integration.secret_hash) is not None


def test_touch_last_used_updates_timestamp(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
) -> None:
    key = api_key_repo.create(make_key(key_owner.id), scopes=frozenset(), grants=())
    used_at = datetime(2026, 7, 17, 12, 34, 56, 987654, tzinfo=UTC)

    first_cutoff = used_at - timedelta(minutes=5)
    assert api_key_repo.touch_last_used(key.id, used_at, first_cutoff) is True
    assert api_key_repo.touch_last_used(key.id + 999, used_at, first_cutoff) is False
    assert api_key_repo.touch_last_used(key.id, used_at + timedelta(minutes=1), used_at - timedelta(minutes=4)) is False
    assert api_key_repo.touch_last_used(key.id, used_at + timedelta(minutes=5), used_at) is True
    loaded = api_key_repo.get_by_secret_hash(key.secret_hash)
    assert loaded is not None
    assert loaded.last_used_at == used_at + timedelta(minutes=5)


def test_key_uniqueness_and_owner_delete_cascade(
    api_key_repo: SQLAlchemyAPIKeyRepository,
    key_owner: User,
    db_connection: Connection,
) -> None:
    saved = api_key_repo.create(
        make_key(key_owner.id),
        scopes=frozenset({"profile:read"}),
        grants=(APIKeyGrant(resource_type="user", resource_id=key_owner.id),),
    )

    with pytest.raises(APIKeyPersistenceError):
        api_key_repo.create(
            make_key(
                key_owner.id,
                uuid=saved.uuid,
                secret_hash=b"u" * 32,
            ),
            scopes=frozenset(),
            grants=(),
        )

    db_connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": key_owner.id})
    db_connection.commit()
    assert api_key_repo.get_by_secret_hash(saved.secret_hash) is None
