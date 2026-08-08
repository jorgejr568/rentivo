from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, create_engine, text

from rentivo.jobs import registry
from rentivo.jobs.base import JobContext
from rentivo.jobs.handlers import auth_cleanup
from rentivo.jobs.payloads import AuthCleanupPayload
from tests.conftest import JOBS_TABLE_DDL

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
CONTEXT = JobContext(ulid="01ARZ3NDEKTSV4RRFFQ69G5FAV", attempts=1)


def _cleanup(payload: dict) -> dict[str, int]:
    """Decode a stored payload the way the registry does, then run the handler."""
    return auth_cleanup.handle_auth_cleanup(AuthCleanupPayload.model_validate(payload), CONTEXT)


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
        connection.execute(text(JOBS_TABLE_DDL))
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


def _seed_job(
    engine: Engine,
    ulid: str,
    *,
    status: str,
    updated_at: datetime,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO jobs (ulid, job_type, payload, status, attempts, max_attempts, "
                "run_after, created_at, updated_at) "
                "VALUES (:ulid, 'email.send', '{}', :status, 0, 5, :updated_at, :updated_at, :updated_at)"
            ),
            {
                "ulid": ulid,
                "status": status,
                "updated_at": updated_at.replace(tzinfo=None),
            },
        )


def _remaining_job_ulids(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return list(connection.execute(text("SELECT ulid FROM jobs ORDER BY id")).scalars())


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

    result = _cleanup({"now": "2026-07-17T12:00:00Z"})

    assert result == {"login_tokens_deleted": 2, "challenges_deleted": 3, "jobs_deleted": 0}
    assert _remaining_ids(cleanup_engine, "api_keys") == [3, 4]
    assert _remaining_ids(cleanup_engine, "auth_challenges") == [4]


def test_cleanup_is_idempotent_when_retried(
    cleanup_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_api_key(cleanup_engine, 1, is_login_token=True, expires_at=NOW)
    _seed_challenge(cleanup_engine, 1, expires_at=NOW)
    monkeypatch.setattr(auth_cleanup, "get_engine", lambda: cleanup_engine, raising=False)

    first = _cleanup({"now": NOW.isoformat()})
    second = _cleanup({"now": NOW.isoformat()})

    assert first == {"login_tokens_deleted": 1, "challenges_deleted": 1, "jobs_deleted": 0}
    assert second == {"login_tokens_deleted": 0, "challenges_deleted": 0, "jobs_deleted": 0}


def test_cleanup_drains_several_login_token_batches_in_a_single_run(
    cleanup_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for row_id in range(1, 6):
        _seed_api_key(cleanup_engine, row_id, is_login_token=True, expires_at=NOW)
    _seed_api_key(cleanup_engine, 6, is_login_token=True, expires_at=NOW + timedelta(minutes=1))
    monkeypatch.setattr(auth_cleanup, "get_engine", lambda: cleanup_engine, raising=False)
    monkeypatch.setattr(auth_cleanup, "AUTH_CLEANUP_BATCH_SIZE", 2, raising=False)

    result = _cleanup({"now": NOW.isoformat()})

    assert result["login_tokens_deleted"] == 5
    assert _remaining_ids(cleanup_engine, "api_keys") == [6]


def test_cleanup_drains_several_challenge_batches_in_a_single_run(
    cleanup_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for row_id in range(1, 6):
        _seed_challenge(cleanup_engine, row_id, expires_at=NOW)
    _seed_challenge(cleanup_engine, 6, expires_at=NOW + timedelta(minutes=1))
    monkeypatch.setattr(auth_cleanup, "get_engine", lambda: cleanup_engine, raising=False)
    monkeypatch.setattr(auth_cleanup, "AUTH_CLEANUP_BATCH_SIZE", 2, raising=False)

    result = _cleanup({"now": NOW.isoformat()})

    assert result["challenges_deleted"] == 5
    assert _remaining_ids(cleanup_engine, "auth_challenges") == [6]


def test_cleanup_applies_the_purge_cap_to_each_table_independently(
    cleanup_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for row_id in range(1, 4):
        _seed_api_key(cleanup_engine, row_id, is_login_token=True, expires_at=NOW)
        _seed_challenge(cleanup_engine, row_id, expires_at=NOW)
    old = NOW - timedelta(days=365)
    for n in range(3):
        _seed_job(cleanup_engine, f"OLD{n}", status="succeeded", updated_at=old)
    monkeypatch.setattr(auth_cleanup, "get_engine", lambda: cleanup_engine, raising=False)
    monkeypatch.setattr(auth_cleanup.settings, "job_retention_days", 30)
    monkeypatch.setattr(auth_cleanup, "AUTH_CLEANUP_BATCH_SIZE", 2, raising=False)
    monkeypatch.setattr(auth_cleanup, "AUTH_CLEANUP_MAX_PURGED_ROWS", 2, raising=False)

    result = _cleanup({"now": NOW.isoformat()})

    # The cap is a per-table budget, so a backlog in one table cannot starve
    # the others: each stops at 2 and leaves its last row for the next run.
    assert result == {"login_tokens_deleted": 2, "challenges_deleted": 2, "jobs_deleted": 2}
    assert _remaining_ids(cleanup_engine, "api_keys") == [3]
    assert _remaining_ids(cleanup_engine, "auth_challenges") == [3]
    assert _remaining_job_ulids(cleanup_engine) == ["OLD2"]


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

    result = _cleanup({})

    assert result["login_tokens_deleted"] == 1


def test_cleanup_purges_only_old_terminal_state_jobs(
    cleanup_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_cleanup, "get_engine", lambda: cleanup_engine, raising=False)
    monkeypatch.setattr(auth_cleanup.settings, "job_retention_days", 30)
    old = datetime(2026, 1, 1, tzinfo=UTC)
    recent = datetime(2026, 7, 30, tzinfo=UTC)
    _seed_job(cleanup_engine, "OLD_OK", status="succeeded", updated_at=old)
    _seed_job(cleanup_engine, "OLD_FAIL", status="failed", updated_at=old)
    _seed_job(cleanup_engine, "OLD_PENDING", status="pending", updated_at=old)
    _seed_job(cleanup_engine, "OLD_RUNNING", status="running", updated_at=old)
    _seed_job(cleanup_engine, "NEW_OK", status="succeeded", updated_at=recent)

    result = _cleanup({"now": "2026-07-31T00:00:00Z"})

    assert result["jobs_deleted"] == 2
    assert _remaining_job_ulids(cleanup_engine) == ["OLD_PENDING", "OLD_RUNNING", "NEW_OK"]


def test_cleanup_purges_jobs_updated_exactly_on_the_retention_cutoff(
    cleanup_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_cleanup, "get_engine", lambda: cleanup_engine, raising=False)
    monkeypatch.setattr(auth_cleanup.settings, "job_retention_days", 30)
    cutoff = datetime(2026, 7, 1, tzinfo=UTC)
    _seed_job(cleanup_engine, "ON_CUTOFF", status="succeeded", updated_at=cutoff)
    _seed_job(
        cleanup_engine,
        "AFTER_CUTOFF",
        status="succeeded",
        updated_at=cutoff + timedelta(seconds=1),
    )

    result = _cleanup({"now": "2026-07-31T00:00:00Z"})

    assert result["jobs_deleted"] == 1
    assert _remaining_job_ulids(cleanup_engine) == ["AFTER_CUTOFF"]


@pytest.mark.parametrize("retention_days", [0, -1])
def test_cleanup_skips_the_job_purge_when_retention_is_disabled(
    cleanup_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    retention_days: int,
) -> None:
    monkeypatch.setattr(auth_cleanup, "get_engine", lambda: cleanup_engine, raising=False)
    monkeypatch.setattr(auth_cleanup.settings, "job_retention_days", retention_days)
    old = datetime(2026, 1, 1, tzinfo=UTC)
    _seed_job(cleanup_engine, "OLD_OK", status="succeeded", updated_at=old)

    result = _cleanup({"now": "2026-07-31T00:00:00Z"})

    assert result["jobs_deleted"] == 0
    assert _remaining_job_ulids(cleanup_engine) == ["OLD_OK"]


def test_cleanup_delete_rechecks_the_purgeable_conditions(
    cleanup_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_cleanup, "get_engine", lambda: cleanup_engine, raising=False)
    monkeypatch.setattr(auth_cleanup.settings, "job_retention_days", 30)
    monkeypatch.setattr(
        auth_cleanup,
        "_PURGEABLE_JOB_IDS",
        text("SELECT id FROM jobs WHERE updated_at <= :cutoff OR status = 'running' ORDER BY id LIMIT :limit"),
        raising=False,
    )
    old = datetime(2026, 1, 1, tzinfo=UTC)
    _seed_job(cleanup_engine, "OLD_OK", status="succeeded", updated_at=old)
    _seed_job(cleanup_engine, "OLD_RUNNING", status="running", updated_at=old)

    result = _cleanup({"now": "2026-07-31T00:00:00Z"})

    assert result["jobs_deleted"] == 1
    assert _remaining_job_ulids(cleanup_engine) == ["OLD_RUNNING"]


def test_cleanup_drains_several_job_batches_in_a_single_run(
    cleanup_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_cleanup, "get_engine", lambda: cleanup_engine, raising=False)
    monkeypatch.setattr(auth_cleanup.settings, "job_retention_days", 30)
    monkeypatch.setattr(auth_cleanup, "AUTH_CLEANUP_BATCH_SIZE", 2, raising=False)
    old = datetime(2026, 1, 1, tzinfo=UTC)
    for n in range(5):
        _seed_job(cleanup_engine, f"OLD{n}", status="succeeded", updated_at=old)
    _seed_job(cleanup_engine, "NEW_OK", status="succeeded", updated_at=datetime(2026, 7, 30, tzinfo=UTC))

    result = _cleanup({"now": "2026-07-31T00:00:00Z"})

    assert result["jobs_deleted"] == 5
    assert _remaining_job_ulids(cleanup_engine) == ["NEW_OK"]


def test_cleanup_stops_at_the_purge_cap_and_resumes_on_the_next_run(
    cleanup_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_cleanup, "get_engine", lambda: cleanup_engine, raising=False)
    monkeypatch.setattr(auth_cleanup.settings, "job_retention_days", 30)
    monkeypatch.setattr(auth_cleanup, "AUTH_CLEANUP_BATCH_SIZE", 2, raising=False)
    monkeypatch.setattr(auth_cleanup, "AUTH_CLEANUP_MAX_PURGED_ROWS", 4, raising=False)
    old = datetime(2026, 1, 1, tzinfo=UTC)
    for n in range(6):
        _seed_job(cleanup_engine, f"OLD{n}", status="succeeded", updated_at=old)

    first = _cleanup({"now": "2026-07-31T00:00:00Z"})

    assert first["jobs_deleted"] == 4
    assert len(_remaining_job_ulids(cleanup_engine)) == 2

    second = _cleanup({"now": "2026-07-31T00:00:00Z"})

    assert second["jobs_deleted"] == 2
    assert _remaining_job_ulids(cleanup_engine) == []
