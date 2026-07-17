import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

from rentivo.repositories.sqlalchemy.auth_rate_limit import SQLAlchemyAuthRateLimitRepository


def _repository(db_connection) -> SQLAlchemyAuthRateLimitRepository:
    db_connection.execute(
        text(
            "CREATE TABLE auth_rate_limits ("
            "action VARCHAR(32) NOT NULL, "
            "identity_hash BLOB NOT NULL, "
            "attempts INTEGER NOT NULL, "
            "window_started_at DATETIME NOT NULL, "
            "expires_at DATETIME NOT NULL, "
            "PRIMARY KEY (action, identity_hash))"
        )
    )
    db_connection.commit()
    return SQLAlchemyAuthRateLimitRepository(db_connection)


def test_reserve_is_shared_bounded_and_resets_after_expiry(db_connection) -> None:
    repository = _repository(db_connection)
    identity_hash = b"a" * 32
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)

    assert repository.reserve(action="login", identity_hash=identity_hash, limit=2, window_seconds=60, now=now)
    assert repository.reserve(action="login", identity_hash=identity_hash, limit=2, window_seconds=60, now=now)
    assert not repository.reserve(action="login", identity_hash=identity_hash, limit=2, window_seconds=60, now=now)
    assert repository.reserve(
        action="login",
        identity_hash=identity_hash,
        limit=2,
        window_seconds=60,
        now=now + timedelta(seconds=60),
    )


def test_clear_removes_only_the_selected_action_and_identity(db_connection) -> None:
    repository = _repository(db_connection)
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    for action in ("login", "password_reset"):
        assert repository.reserve(
            action=action,
            identity_hash=b"a" * 32,
            limit=1,
            window_seconds=60,
            now=now,
        )

    repository.clear(action="login", identity_hash=b"a" * 32)

    assert repository.reserve(action="login", identity_hash=b"a" * 32, limit=1, window_seconds=60, now=now)
    assert not repository.reserve(
        action="password_reset",
        identity_hash=b"a" * 32,
        limit=1,
        window_seconds=60,
        now=now,
    )


def test_reservation_cleans_expired_identities_in_a_bounded_batch(db_connection) -> None:
    repository = _repository(db_connection)
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    for index in range(3):
        assert repository.reserve(
            action="login",
            identity_hash=bytes([index]) * 32,
            limit=1,
            window_seconds=1,
            now=now,
        )

    assert repository.reserve(
        action="login",
        identity_hash=b"current".ljust(32, b"!"),
        limit=1,
        window_seconds=60,
        now=now + timedelta(seconds=2),
    )

    rows = db_connection.execute(text("SELECT identity_hash FROM auth_rate_limits")).scalars().all()
    assert rows == [b"current".ljust(32, b"!")]


def test_delete_expired_honors_its_batch_limit(db_connection) -> None:
    repository = _repository(db_connection)
    expired = datetime(2026, 7, 17, 12)
    for index in range(3):
        db_connection.execute(
            text(
                "INSERT INTO auth_rate_limits "
                "(action, identity_hash, attempts, window_started_at, expires_at) "
                "VALUES ('login', :identity_hash, 1, :started_at, :expires_at)"
            ),
            {
                "identity_hash": bytes([index]) * 32,
                "started_at": expired - timedelta(minutes=1),
                "expires_at": expired,
            },
        )
    db_connection.commit()

    assert repository.delete_expired(cutoff=expired, limit=2) == 2
    assert db_connection.execute(text("SELECT COUNT(*) FROM auth_rate_limits")).scalar_one() == 1


def test_naive_database_time_is_supported(db_connection) -> None:
    repository = _repository(db_connection)

    assert repository.reserve(
        action="login",
        identity_hash=b"n" * 32,
        limit=1,
        window_seconds=60,
        now=datetime(2026, 7, 17, 12),
    )


def test_reserve_rolls_back_unexpected_database_failures(db_connection) -> None:
    repository = _repository(db_connection)
    with patch.object(repository, "_reserve_once", side_effect=RuntimeError("database failed")):
        with patch.object(db_connection, "rollback") as rollback:
            with pytest.raises(RuntimeError, match="database failed"):
                repository.reserve(
                    action="login",
                    identity_hash=b"a" * 32,
                    limit=1,
                    window_seconds=60,
                    now=datetime.now(UTC),
                )

    rollback.assert_called_once_with()


def test_clear_rolls_back_unexpected_database_failures() -> None:
    connection = MagicMock()
    connection.execute.side_effect = RuntimeError("database failed")
    repository = SQLAlchemyAuthRateLimitRepository(connection)

    with pytest.raises(RuntimeError, match="database failed"):
        repository.clear(action="login", identity_hash=b"a" * 32)

    connection.rollback.assert_called_once_with()


def test_delete_expired_rolls_back_unexpected_database_failures() -> None:
    connection = MagicMock()
    connection.execute.side_effect = RuntimeError("database failed")
    repository = SQLAlchemyAuthRateLimitRepository(connection)

    with pytest.raises(RuntimeError, match="database failed"):
        repository.delete_expired(cutoff=datetime.now(UTC), limit=100)

    connection.rollback.assert_called_once_with()


def test_cleanup_failure_does_not_fail_an_enforced_reservation(db_connection) -> None:
    repository = _repository(db_connection)
    with patch.object(repository, "delete_expired", side_effect=RuntimeError("cleanup failed")):
        assert repository.reserve(
            action="login",
            identity_hash=b"a" * 32,
            limit=1,
            window_seconds=60,
            now=datetime.now(UTC),
        )


def test_parallel_first_reservations_are_atomic_across_connections(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'rate-limits.db'}", connect_args={"timeout": 30})
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE auth_rate_limits ("
                "action VARCHAR(32) NOT NULL, identity_hash BLOB NOT NULL, attempts INTEGER NOT NULL, "
                "window_started_at DATETIME NOT NULL, expires_at DATETIME NOT NULL, "
                "PRIMARY KEY (action, identity_hash))"
            )
        )

    now = datetime(2026, 7, 17, 12, tzinfo=UTC)

    def reserve() -> bool:
        with engine.connect() as connection:
            return SQLAlchemyAuthRateLimitRepository(connection).reserve(
                action="login",
                identity_hash=b"parallel".ljust(32, b"!"),
                limit=5,
                window_seconds=60,
                now=now,
            )

    try:
        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(lambda _index: reserve(), range(20)))

        assert results.count(True) == 5
        assert results.count(False) == 15
    finally:
        engine.dispose()


@pytest.mark.skipif(
    not os.getenv("RENTIVO_TEST_MARIADB_URL"),
    reason="Set RENTIVO_TEST_MARIADB_URL to run the real MariaDB concurrency contract",
)
def test_parallel_first_reservations_are_atomic_on_mariadb() -> None:
    engine = create_engine(os.environ["RENTIVO_TEST_MARIADB_URL"], pool_size=20, max_overflow=0)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS auth_rate_limits"))
        connection.execute(
            text(
                "CREATE TABLE auth_rate_limits ("
                "action VARCHAR(32) NOT NULL, identity_hash BINARY(32) NOT NULL, attempts INTEGER NOT NULL, "
                "window_started_at DATETIME(6) NOT NULL, expires_at DATETIME(6) NOT NULL, "
                "PRIMARY KEY (action, identity_hash)) ENGINE=InnoDB"
            )
        )

    now = datetime(2026, 7, 17, 12, tzinfo=UTC)

    def reserve() -> bool:
        with engine.connect() as connection:
            return SQLAlchemyAuthRateLimitRepository(connection).reserve(
                action="login",
                identity_hash=b"mariadb".ljust(32, b"!"),
                limit=5,
                window_seconds=60,
                now=now,
            )

    try:
        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(lambda _index: reserve(), range(20)))
        assert results.count(True) == 5
        assert results.count(False) == 15
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS auth_rate_limits"))
        engine.dispose()
