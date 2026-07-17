from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, create_engine, text

from rentivo.jobs import registry
from rentivo.jobs.base import PermanentJobError
from rentivo.jobs.handlers import auth_cleanup

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


@pytest.fixture()
def cleanup_engine() -> Engine:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE api_keys ("
                "id INTEGER PRIMARY KEY, "
                "uuid VARCHAR(26) NOT NULL, "
                "is_login_token BOOLEAN NOT NULL, "
                "expires_at DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE auth_challenges ("
                "id INTEGER PRIMARY KEY, "
                "uuid VARCHAR(26) NOT NULL, "
                "expires_at DATETIME NOT NULL, "
                "consumed_at DATETIME)"
            )
        )
    yield engine
    engine.dispose()


def _seed_api_key(
    engine: Engine,
    row_id: int,
    *,
    is_login_token: bool,
    expires_at: datetime,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO api_keys (id, uuid, is_login_token, expires_at) "
                "VALUES (:id, :uuid, :is_login_token, :expires_at)"
            ),
            {
                "id": row_id,
                "uuid": f"api-key-{row_id}",
                "is_login_token": is_login_token,
                "expires_at": expires_at.replace(tzinfo=None),
            },
        )


def _seed_challenge(
    engine: Engine,
    row_id: int,
    *,
    expires_at: datetime,
    consumed_at: datetime | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO auth_challenges (id, uuid, expires_at, consumed_at) "
                "VALUES (:id, :uuid, :expires_at, :consumed_at)"
            ),
            {
                "id": row_id,
                "uuid": f"challenge-{row_id}",
                "expires_at": expires_at.replace(tzinfo=None),
                "consumed_at": None if consumed_at is None else consumed_at.replace(tzinfo=None),
            },
        )


def _remaining_ids(engine: Engine, table: str) -> list[int]:
    with engine.connect() as connection:
        return list(connection.execute(text(f"SELECT id FROM {table} ORDER BY id")).scalars())


def test_auth_cleanup_handler_is_registered() -> None:
    registry._REGISTRY.pop("auth.cleanup", None)

    handler = registry.get("auth.cleanup")

    assert handler is not None
    assert handler.__name__ == "handle_auth_cleanup"


def test_cleanup_removes_only_expired_login_tokens_and_expired_or_consumed_challenges(
    cleanup_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_api_key(cleanup_engine, 1, is_login_token=True, expires_at=NOW - timedelta(seconds=1))
    _seed_api_key(cleanup_engine, 2, is_login_token=True, expires_at=NOW)
    _seed_api_key(cleanup_engine, 3, is_login_token=True, expires_at=NOW + timedelta(seconds=1))
    _seed_api_key(cleanup_engine, 4, is_login_token=False, expires_at=NOW - timedelta(days=1))
    _seed_challenge(cleanup_engine, 1, expires_at=NOW - timedelta(seconds=1))
    _seed_challenge(cleanup_engine, 2, expires_at=NOW)
    _seed_challenge(cleanup_engine, 3, expires_at=NOW + timedelta(minutes=1), consumed_at=NOW)
    _seed_challenge(cleanup_engine, 4, expires_at=NOW + timedelta(minutes=1))
    monkeypatch.setattr(auth_cleanup, "get_engine", lambda: cleanup_engine, raising=False)

    result = auth_cleanup.handle_auth_cleanup({"now": "2026-07-17T12:00:00Z"})

    assert result == {"login_tokens_deleted": 2, "challenges_deleted": 3}
    assert _remaining_ids(cleanup_engine, "api_keys") == [3, 4]
    assert _remaining_ids(cleanup_engine, "auth_challenges") == [4]


def test_cleanup_is_idempotent_when_retried(
    cleanup_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_api_key(cleanup_engine, 1, is_login_token=True, expires_at=NOW)
    _seed_challenge(cleanup_engine, 1, expires_at=NOW)
    monkeypatch.setattr(auth_cleanup, "get_engine", lambda: cleanup_engine, raising=False)

    first = auth_cleanup.handle_auth_cleanup({"now": NOW.isoformat()})
    second = auth_cleanup.handle_auth_cleanup({"now": NOW.isoformat()})

    assert first == {"login_tokens_deleted": 1, "challenges_deleted": 1}
    assert second == {"login_tokens_deleted": 0, "challenges_deleted": 0}


def test_cleanup_honors_the_batch_limit_for_each_table(
    cleanup_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for row_id in range(1, 4):
        _seed_api_key(cleanup_engine, row_id, is_login_token=True, expires_at=NOW)
        _seed_challenge(cleanup_engine, row_id, expires_at=NOW)
    monkeypatch.setattr(auth_cleanup, "get_engine", lambda: cleanup_engine, raising=False)
    monkeypatch.setattr(auth_cleanup, "AUTH_CLEANUP_BATCH_SIZE", 2, raising=False)

    result = auth_cleanup.handle_auth_cleanup({"now": NOW.isoformat()})

    assert result == {"login_tokens_deleted": 2, "challenges_deleted": 2}
    assert _remaining_ids(cleanup_engine, "api_keys") == [3]
    assert _remaining_ids(cleanup_engine, "auth_challenges") == [3]


def test_cleanup_uses_current_utc_time_when_payload_omits_now(
    cleanup_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_api_key(
        cleanup_engine,
        1,
        is_login_token=True,
        expires_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(auth_cleanup, "get_engine", lambda: cleanup_engine, raising=False)

    result = auth_cleanup.handle_auth_cleanup({})

    assert result["login_tokens_deleted"] == 1


@pytest.mark.parametrize("now", [123, "not-a-timestamp", "2026-07-17T12:00:00"])
def test_cleanup_rejects_invalid_or_naive_timestamps(now: object) -> None:
    with pytest.raises(PermanentJobError, match="UTC timestamp"):
        auth_cleanup.handle_auth_cleanup({"now": now})
