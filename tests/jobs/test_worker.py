from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from rentivo.jobs import registry
from rentivo.jobs.base import Job, PermanentJobError
from rentivo.jobs.worker import _BACKOFF_SECONDS, Worker, next_run_after


@pytest.fixture(autouse=True)
def _clean_registry():
    registry._REGISTRY.clear()
    yield
    registry._REGISTRY.clear()


def _make_job(attempts: int = 1, max_attempts: int = 5) -> Job:
    return Job(id=1, ulid="01HXYZ", job_type="t.test", payload={}, attempts=attempts, max_attempts=max_attempts)


class TestNextRunAfter:
    @pytest.mark.parametrize(
        "attempts,expected_seconds",
        [(1, 60), (2, 300), (3, 900), (4, 3600), (5, 21600), (6, 21600)],
    )
    def test_backoff_ladder(self, attempts: int, expected_seconds: int):
        now = datetime(2030, 1, 1, 0, 0, 0)
        result = next_run_after(attempts, now)
        assert result == now + timedelta(seconds=expected_seconds)

    def test_backoff_constant_shape(self):
        assert _BACKOFF_SECONDS == (60, 300, 900, 3600, 21600)


class TestWorkerTick:
    def test_tick_returns_zero_when_no_jobs(self):
        repo = MagicMock()
        repo.claim_batch.return_value = []
        w = Worker(repo, MagicMock(), worker_id="t:1")
        assert w.tick() == 0

    def test_tick_marks_succeeded_on_clean_handler(self):
        called = {"count": 0}

        @registry.register("t.test")
        def handler(payload):
            called["count"] += 1

        job = _make_job(attempts=1)
        repo = MagicMock()
        repo.claim_batch.return_value = [job]
        audit = MagicMock()
        w = Worker(repo, audit, worker_id="t:1")

        assert w.tick() == 1
        assert called["count"] == 1
        repo.mark_succeeded.assert_called_once_with(1)
        repo.reschedule.assert_not_called()
        repo.mark_failed.assert_not_called()

        from rentivo.models.audit_log import AuditEventType

        audit.safe_log.assert_called_once()
        assert audit.safe_log.call_args.kwargs["event_type"] == AuditEventType.JOB_SUCCEEDED
        assert audit.safe_log.call_args.kwargs["source"] == "worker"

    def test_tick_reschedules_on_retryable_exception(self):
        @registry.register("t.test")
        def handler(payload):
            raise RuntimeError("boom")

        job = _make_job(attempts=1)
        repo = MagicMock()
        repo.claim_batch.return_value = [job]
        audit = MagicMock()
        w = Worker(repo, audit, worker_id="t:1")

        w.tick()

        repo.mark_failed.assert_not_called()
        repo.reschedule.assert_called_once()
        call = repo.reschedule.call_args
        assert call.args[0] == 1
        assert "boom" in call.args[2]
        from rentivo.models.audit_log import AuditEventType

        assert audit.safe_log.call_args.kwargs["event_type"] == AuditEventType.JOB_RETRY_SCHEDULED

    def test_tick_marks_failed_when_attempts_reached_max(self):
        @registry.register("t.test")
        def handler(payload):
            raise RuntimeError("boom")

        job = _make_job(attempts=5, max_attempts=5)
        repo = MagicMock()
        repo.claim_batch.return_value = [job]
        audit = MagicMock()
        w = Worker(repo, audit, worker_id="t:1")

        w.tick()

        repo.reschedule.assert_not_called()
        repo.mark_failed.assert_called_once()
        from rentivo.models.audit_log import AuditEventType

        assert audit.safe_log.call_args.kwargs["event_type"] == AuditEventType.JOB_FAILED

    def test_tick_dead_letters_immediately_on_permanent_error(self):
        @registry.register("t.test")
        def handler(payload):
            raise PermanentJobError("template missing")

        job = _make_job(attempts=1, max_attempts=5)
        repo = MagicMock()
        repo.claim_batch.return_value = [job]
        audit = MagicMock()
        w = Worker(repo, audit, worker_id="t:1")

        w.tick()

        repo.reschedule.assert_not_called()
        repo.mark_failed.assert_called_once_with(1, "template missing")

    def test_tick_dead_letters_when_no_handler_registered(self):
        job = _make_job(attempts=1)
        job = Job(
            id=job.id,
            ulid=job.ulid,
            job_type="missing.handler",
            payload={},
            attempts=job.attempts,
            max_attempts=job.max_attempts,
        )
        repo = MagicMock()
        repo.claim_batch.return_value = [job]
        audit = MagicMock()
        w = Worker(repo, audit, worker_id="t:1")

        w.tick()

        repo.mark_failed.assert_called_once()
        err = repo.mark_failed.call_args.args[1]
        assert "missing.handler" in err

    def test_tick_reschedules_with_timezone_aware_datetime(self):
        """Regression: the worker must pass an aware datetime to repo.reschedule
        so the repository's SP_TZ conversion runs. Naive UTC would be interpreted
        as SP_TZ wall-clock by the repo and misfire retries by ~3h."""

        @registry.register("t.test")
        def handler(payload):
            raise RuntimeError("boom")

        job = _make_job(attempts=1)
        repo = MagicMock()
        repo.claim_batch.return_value = [job]
        w = Worker(repo, MagicMock(), worker_id="t:1")

        w.tick()

        next_run = repo.reschedule.call_args.args[1]
        assert next_run.tzinfo is not None, "next_run must be timezone-aware"

    def test_tick_truncates_extremely_long_errors(self):
        @registry.register("t.test")
        def handler(payload):
            raise RuntimeError("x" * 10_000)

        job = _make_job(attempts=1)
        repo = MagicMock()
        repo.claim_batch.return_value = [job]
        w = Worker(repo, MagicMock(), worker_id="t:1")

        w.tick()
        err = repo.reschedule.call_args.args[2]
        assert len(err) <= 4096


class TestWorkerLoop:
    def test_run_forever_exits_when_stop_called(self):
        repo = MagicMock()
        repo.claim_batch.return_value = []
        w = Worker(repo, MagicMock(), worker_id="t:1", idle_sleep_seconds=0.01)
        w.stop()  # set _stopping before run starts
        w.run_forever()
        # If the loop does not exit, the test hangs and pytest times out.

    def test_run_forever_drains_batch_then_idles_until_stopped(self, monkeypatch):
        repo = MagicMock()
        repo.claim_batch.return_value = []
        w = Worker(repo, MagicMock(), worker_id="t:1", idle_sleep_seconds=0.01)

        sleep_calls: list[float] = []

        def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            w.stop()

        monkeypatch.setattr("rentivo.jobs.worker.time.sleep", fake_sleep)
        w.run_forever()

        assert sleep_calls == [0.01]
        assert repo.claim_batch.call_count == 1

    def test_default_worker_id_includes_hostname_and_pid(self):
        repo = MagicMock()
        w = Worker(repo, MagicMock())
        assert ":" in w.worker_id
        host, pid = w.worker_id.split(":", 1)
        assert host
        assert pid.isdigit()


def test_fail_invokes_registered_hook_with_payload():
    from rentivo.jobs import registry
    from rentivo.jobs.base import Job
    from rentivo.jobs.worker import Worker

    captured: list[dict] = []

    @registry.register_on_fail("pdf.render")
    def _hook(payload: dict) -> None:
        captured.append(payload)

    try:
        repo = MagicMock()
        audit = MagicMock()
        worker = Worker(repo, audit)
        job = Job(
            id=99,
            ulid="01HXYZ",
            job_type="pdf.render",
            payload={"bill_id": 7},
            attempts=3,
            max_attempts=3,
        )
        worker._fail(job, "boom")

        repo.mark_failed.assert_called_once_with(99, "boom")
        assert captured == [{"bill_id": 7}]
    finally:
        registry._FAIL_HOOKS.clear()


def test_fail_swallows_hook_exception(caplog):
    from rentivo.jobs import registry
    from rentivo.jobs.base import Job
    from rentivo.jobs.worker import Worker

    @registry.register_on_fail("pdf.render")
    def _hook(payload: dict) -> None:
        raise RuntimeError("hook bug")

    try:
        repo = MagicMock()
        audit = MagicMock()
        worker = Worker(repo, audit)
        job = Job(
            id=99,
            ulid="01HXYZ",
            job_type="pdf.render",
            payload={"bill_id": 7},
            attempts=3,
            max_attempts=3,
        )
        # Must not raise; hook errors are isolated.
        worker._fail(job, "boom")
        repo.mark_failed.assert_called_once_with(99, "boom")
    finally:
        registry._FAIL_HOOKS.clear()


def test_fail_no_hook_registered_does_not_raise():
    from rentivo.jobs import registry
    from rentivo.jobs.base import Job
    from rentivo.jobs.worker import Worker

    registry._FAIL_HOOKS.clear()
    repo = MagicMock()
    audit = MagicMock()
    worker = Worker(repo, audit)
    job = Job(
        id=99,
        ulid="01HXYZ",
        job_type="pdf.render",
        payload={"bill_id": 7},
        attempts=3,
        max_attempts=3,
    )
    worker._fail(job, "boom")
    repo.mark_failed.assert_called_once_with(99, "boom")
