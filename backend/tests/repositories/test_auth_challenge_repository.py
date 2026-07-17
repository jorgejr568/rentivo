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

from rentivo.models.auth_challenge import AuthChallenge
from rentivo.models.user import User
from rentivo.observability import instrument_sqlalchemy, span, tracing
from rentivo.repositories.base import AuthChallengePersistenceError
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyAuthChallengeRepository,
    SQLAlchemyUserRepository,
)

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
CHALLENGE_UUID = "01K0AUTHCHALLENGE000000000"


@pytest.fixture()
def auth_challenge_repo(db_connection: Connection) -> SQLAlchemyAuthChallengeRepository:
    db_connection.execute(
        text(
            """
            CREATE TABLE auth_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid VARCHAR(26) NOT NULL,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                phase VARCHAR(32) NOT NULL,
                nonce_hash BINARY(32) NOT NULL,
                allowed_methods TEXT NOT NULL,
                webauthn_challenge BLOB,
                failures INTEGER NOT NULL DEFAULT 0,
                expires_at DATETIME NOT NULL,
                created_at DATETIME NOT NULL,
                consumed_at DATETIME
            )
            """
        )
    )
    db_connection.execute(text("CREATE UNIQUE INDEX ix_auth_challenges_uuid ON auth_challenges (uuid)"))
    db_connection.execute(text("CREATE INDEX ix_auth_challenges_user_id ON auth_challenges (user_id)"))
    db_connection.execute(text("CREATE INDEX ix_auth_challenges_expires_at ON auth_challenges (expires_at)"))
    db_connection.commit()
    return SQLAlchemyAuthChallengeRepository(db_connection)


@pytest.fixture()
def challenge_owner(user_repo: SQLAlchemyUserRepository) -> User:
    return user_repo.create(User(email="challenge-owner@example.com", password_hash="x"))


def make_challenge(user_id: int | None, **overrides: object) -> AuthChallenge:
    defaults: dict[str, object] = {
        "uuid": CHALLENGE_UUID,
        "user_id": user_id,
        "phase": "mfa",
        "nonce_hash": b"n" * 32,
        "allowed_methods": ("totp", "passkey"),
        "webauthn_challenge": b"webauthn-options-challenge",
        "expires_at": NOW + timedelta(minutes=5),
        "created_at": NOW,
    }
    defaults.update(overrides)
    return AuthChallenge(**defaults)


def test_repository_round_trips_challenge_fields(
    auth_challenge_repo: SQLAlchemyAuthChallengeRepository,
    challenge_owner: User,
) -> None:
    challenge = make_challenge(challenge_owner.id)

    saved = auth_challenge_repo.create(challenge)
    loaded = auth_challenge_repo.get_by_uuid(challenge.uuid)

    assert loaded == saved
    assert saved.id is not None
    assert saved.user_id == challenge_owner.id
    assert saved.phase == "mfa"
    assert saved.nonce_hash == b"n" * 32
    assert saved.allowed_methods == ("totp", "passkey")
    assert saved.webauthn_challenge == b"webauthn-options-challenge"
    assert saved.failures == 0
    assert saved.created_at == NOW
    assert saved.expires_at == NOW + timedelta(minutes=5)
    assert saved.created_at.tzinfo is UTC
    assert saved.expires_at.tzinfo is UTC
    assert saved.consumed_at is None


def test_repository_generates_public_ulid_and_supports_optional_webauthn_bytes(
    auth_challenge_repo: SQLAlchemyAuthChallengeRepository,
    challenge_owner: User,
) -> None:
    saved = auth_challenge_repo.create(
        make_challenge(
            challenge_owner.id,
            uuid="",
            allowed_methods=("totp",),
            webauthn_challenge=None,
        )
    )

    assert len(saved.uuid) == 26
    assert saved.allowed_methods == ("totp",)
    assert saved.webauthn_challenge is None
    assert auth_challenge_repo.get_by_uuid("01K0MISSINGCHALLENGE000000") is None


def test_repository_supports_pre_user_oauth_state(
    auth_challenge_repo: SQLAlchemyAuthChallengeRepository,
) -> None:
    saved = auth_challenge_repo.create(
        make_challenge(
            user_id=None,
            phase="oauth",
            allowed_methods=(),
            webauthn_challenge=None,
        )
    )

    assert saved.user_id is None
    assert saved.phase == "oauth"
    assert saved.allowed_methods == ()


def test_repository_failure_count_is_an_atomic_increment(
    auth_challenge_repo: SQLAlchemyAuthChallengeRepository,
    challenge_owner: User,
) -> None:
    saved = auth_challenge_repo.create(make_challenge(challenge_owner.id))

    assert auth_challenge_repo.increment_failures(saved.uuid, "mfa", NOW) is True
    assert auth_challenge_repo.increment_failures(saved.uuid, "mfa", NOW) is True
    assert auth_challenge_repo.increment_failures("01K0MISSINGCHALLENGE000000", "mfa", NOW) is False

    loaded = auth_challenge_repo.get_by_uuid(saved.uuid)
    assert loaded is not None
    assert loaded.failures == 2
    assert loaded.allowed_methods == saved.allowed_methods
    assert loaded.consumed_at is None


def test_repository_consume_is_single_use_before_expiry(
    auth_challenge_repo: SQLAlchemyAuthChallengeRepository,
    challenge_owner: User,
) -> None:
    expires_at = NOW + timedelta(minutes=5)
    saved = auth_challenge_repo.create(make_challenge(challenge_owner.id, expires_at=expires_at))

    consumed_at = expires_at - timedelta(microseconds=1)
    assert auth_challenge_repo.consume(saved.uuid, "mfa", consumed_at) is True
    assert auth_challenge_repo.consume(saved.uuid, "mfa", consumed_at) is False

    loaded = auth_challenge_repo.get_by_uuid(saved.uuid)
    assert loaded is not None
    assert loaded.consumed_at == consumed_at


def test_repository_consume_rejects_expired_or_unknown_challenges(
    auth_challenge_repo: SQLAlchemyAuthChallengeRepository,
    challenge_owner: User,
) -> None:
    expired = auth_challenge_repo.create(
        make_challenge(
            challenge_owner.id,
            uuid="01K0EXPIREDCHALLENGE000000",
            expires_at=NOW,
        )
    )

    assert auth_challenge_repo.consume(expired.uuid, "mfa", NOW) is False
    assert auth_challenge_repo.consume(expired.uuid, "oauth", NOW - timedelta(microseconds=1)) is False
    assert auth_challenge_repo.consume("01K0MISSINGCHALLENGE000000", "mfa", NOW) is False
    loaded = auth_challenge_repo.get_by_uuid(expired.uuid)
    assert loaded is not None
    assert loaded.consumed_at is None


def test_repository_conditionally_sets_webauthn_challenge(
    auth_challenge_repo: SQLAlchemyAuthChallengeRepository,
    challenge_owner: User,
) -> None:
    saved = auth_challenge_repo.create(make_challenge(challenge_owner.id, webauthn_challenge=None))

    assert (
        auth_challenge_repo.set_webauthn_challenge(
            saved.uuid,
            "mfa",
            b"new-webauthn-challenge",
            NOW,
        )
        is True
    )
    loaded = auth_challenge_repo.get_by_uuid(saved.uuid)
    assert loaded is not None
    assert loaded.webauthn_challenge == b"new-webauthn-challenge"


def test_repository_rejects_webauthn_update_for_wrong_phase_expired_or_consumed_challenge(
    auth_challenge_repo: SQLAlchemyAuthChallengeRepository,
    challenge_owner: User,
) -> None:
    saved = auth_challenge_repo.create(make_challenge(challenge_owner.id))

    assert auth_challenge_repo.set_webauthn_challenge(saved.uuid, "oauth", b"wrong", NOW) is False
    assert (
        auth_challenge_repo.set_webauthn_challenge(
            saved.uuid,
            "mfa",
            b"expired",
            saved.expires_at,
        )
        is False
    )
    assert auth_challenge_repo.consume(saved.uuid, "mfa", NOW) is True
    assert auth_challenge_repo.set_webauthn_challenge(saved.uuid, "mfa", b"consumed", NOW) is False


def test_duplicate_uuid_rolls_back_without_replacing_existing_challenge(
    auth_challenge_repo: SQLAlchemyAuthChallengeRepository,
    challenge_owner: User,
) -> None:
    original = auth_challenge_repo.create(make_challenge(challenge_owner.id))

    with pytest.raises(AuthChallengePersistenceError):
        auth_challenge_repo.create(
            make_challenge(
                challenge_owner.id,
                nonce_hash=b"d" * 32,
                allowed_methods=("recovery",),
            )
        )

    loaded = auth_challenge_repo.get_by_uuid(original.uuid)
    assert loaded == original


def test_duplicate_challenge_never_reaches_trace_details(
    auth_challenge_repo: SQLAlchemyAuthChallengeRepository,
    challenge_owner: User,
) -> None:
    nonce_hash = b"S" * 32
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracing._reset_for_tests()
    tracing.configure_tracing(provider=provider)
    instrument_sqlalchemy(auth_challenge_repo.conn.engine)
    try:
        auth_challenge_repo.create(make_challenge(challenge_owner.id))
        exporter.clear()

        with pytest.raises(AuthChallengePersistenceError) as exc_info:
            with span("HTTP POST"):
                auth_challenge_repo.create(make_challenge(challenge_owner.id, nonce_hash=nonce_hash))

        serialized_spans = repr(
            [
                (finished.status.description, [(event.name, dict(event.attributes)) for event in finished.events])
                for finished in exporter.get_finished_spans()
            ]
        )
        assert all(finished.attributes.get("db.system") is None for finished in exporter.get_finished_spans())
        assert nonce_hash.hex() not in serialized_spans
        assert "S" * 32 not in serialized_spans
        formatted_exception = "".join(traceback.format_exception(exc_info.value))
        assert nonce_hash.hex() not in formatted_exception
        assert "S" * 32 not in formatted_exception
        assert exc_info.value.__context__ is None
    finally:
        SQLAlchemyInstrumentor().uninstrument()
        tracing._reset_for_tests()


def test_repository_sanitizes_database_and_rollback_failures() -> None:
    connection = MagicMock()
    connection.execute.side_effect = SQLAlchemyError("S" * 32)
    connection.rollback.side_effect = SQLAlchemyError("R" * 32)
    repository = SQLAlchemyAuthChallengeRepository(connection)
    challenge = make_challenge(user_id=7, nonce_hash=b"S" * 32)

    with pytest.raises(AuthChallengePersistenceError) as exc_info:
        repository.create(challenge)

    formatted_exception = "".join(traceback.format_exception(exc_info.value))
    assert "S" * 32 not in formatted_exception
    assert "R" * 32 not in formatted_exception
    assert challenge.nonce_hash.hex() not in formatted_exception
    assert exc_info.value.__context__ is None
    connection.rollback.assert_called_once_with()


def test_create_rolls_back_and_reraises_non_database_failures() -> None:
    connection = MagicMock()
    connection.execute.side_effect = RuntimeError("non-database failure")
    repository = SQLAlchemyAuthChallengeRepository(connection)

    with pytest.raises(RuntimeError, match="non-database failure"):
        repository.create(make_challenge(user_id=7))

    connection.rollback.assert_called_once_with()


def test_create_fails_safely_when_read_after_write_returns_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = MagicMock()
    repository = SQLAlchemyAuthChallengeRepository(connection)
    monkeypatch.setattr(repository, "get_by_uuid", MagicMock(return_value=None))

    with pytest.raises(AuthChallengePersistenceError, match="persistence failed"):
        repository.create(make_challenge(user_id=7))


@pytest.mark.parametrize(
    ("operation", "args", "message"),
    [
        ("get_by_uuid", (CHALLENGE_UUID,), "lookup failed"),
        ("increment_failures", (CHALLENGE_UUID, "mfa", NOW), "update failed"),
        ("set_webauthn_challenge", (CHALLENGE_UUID, "mfa", b"challenge", NOW), "update failed"),
        ("consume", (CHALLENGE_UUID, "mfa", NOW), "consumption failed"),
    ],
)
def test_repository_operations_sanitize_database_and_rollback_failures(
    operation: str,
    args: tuple[object, ...],
    message: str,
) -> None:
    connection = MagicMock()
    connection.execute.side_effect = SQLAlchemyError("S" * 32)
    connection.rollback.side_effect = SQLAlchemyError("R" * 32)
    repository = SQLAlchemyAuthChallengeRepository(connection)

    with pytest.raises(AuthChallengePersistenceError, match=message) as exc_info:
        getattr(repository, operation)(*args)

    formatted_exception = "".join(traceback.format_exception(exc_info.value))
    assert "S" * 32 not in formatted_exception
    assert "R" * 32 not in formatted_exception
    assert exc_info.value.__context__ is None
    connection.rollback.assert_called_once_with()
