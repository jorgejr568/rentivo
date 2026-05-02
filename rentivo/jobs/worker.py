from __future__ import annotations

import os
import signal
import socket
import time
from datetime import UTC, datetime, timedelta

import structlog

from rentivo.jobs import registry
from rentivo.jobs.base import Job, JobRepository, PermanentJobError
from rentivo.models.audit_log import AuditEventType
from rentivo.services.audit_service import AuditService

logger = structlog.get_logger(__name__)

_BACKOFF_SECONDS: tuple[int, ...] = (60, 300, 900, 3600, 21600)
_MAX_ERROR_LEN = 4096


def next_run_after(attempts: int, now: datetime) -> datetime:
    idx = min(max(attempts, 1) - 1, len(_BACKOFF_SECONDS) - 1)
    return now + timedelta(seconds=_BACKOFF_SECONDS[idx])


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n]


class Worker:
    def __init__(
        self,
        repo: JobRepository,
        audit: AuditService,
        *,
        batch_size: int = 10,
        idle_sleep_seconds: float = 5.0,
        worker_id: str = "",
    ) -> None:
        self.repo = repo
        self.audit = audit
        self.batch_size = batch_size
        self.idle_sleep_seconds = idle_sleep_seconds
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self._stopping = False

    def stop(self) -> None:
        self._stopping = True

    def _install_signal_handlers(self) -> None:
        def _handle(signum, frame):  # pragma: no cover — signal hook
            self.stop()

        signal.signal(signal.SIGTERM, _handle)
        signal.signal(signal.SIGINT, _handle)

    def run_forever(self) -> None:
        self._install_signal_handlers()
        logger.info("worker_started", worker_id=self.worker_id)
        while not self._stopping:
            processed = self.tick()
            if processed == 0 and not self._stopping:
                time.sleep(self.idle_sleep_seconds)
        logger.info("worker_stopped", worker_id=self.worker_id)

    def tick(self) -> int:
        jobs = self.repo.claim_batch(self.batch_size, self.worker_id)
        for job in jobs:
            self._run_one(job)
        return len(jobs)

    def _run_one(self, job: Job) -> None:
        handler = registry.get(job.job_type)
        if handler is None:
            self._fail_permanent(job, f"no handler registered for job_type {job.job_type!r}")
            return
        try:
            handler(job.payload)
        except PermanentJobError as exc:
            self._fail_permanent(job, str(exc))
        except Exception as exc:
            self._reschedule_or_fail(job, exc)
        else:
            self.repo.mark_succeeded(job.id)
            self.audit.safe_log(
                event_type=AuditEventType.JOB_SUCCEEDED,
                source="worker",
                actor_id=None,
                actor_username="",
                entity_type="job",
                entity_uuid=job.ulid,
                previous_state=None,
                new_state={"job_type": job.job_type, "ulid": job.ulid, "attempts": job.attempts},
            )
            logger.info("job_succeeded", ulid=job.ulid, attempts=job.attempts)

    def _fail(self, job: Job, err: str) -> None:
        err = _truncate(err, _MAX_ERROR_LEN)
        self.repo.mark_failed(job.id, err)
        self.audit.safe_log(
            event_type=AuditEventType.JOB_FAILED,
            source="worker",
            actor_id=None,
            actor_username="",
            entity_type="job",
            entity_uuid=job.ulid,
            previous_state=None,
            new_state={"job_type": job.job_type, "ulid": job.ulid, "attempts": job.attempts, "error": err},
        )
        hook = registry.get_fail_hook(job.job_type)
        if hook is not None:
            try:
                hook(job.payload)
            except Exception:
                logger.exception("job_fail_hook_failed", ulid=job.ulid, job_type=job.job_type)
        logger.warning("job_failed", ulid=job.ulid, attempts=job.attempts, error=err)

    def _fail_permanent(self, job: Job, err: str) -> None:
        self._fail(job, err)

    def _reschedule_or_fail(self, job: Job, exc: Exception) -> None:
        err = _truncate(repr(exc), _MAX_ERROR_LEN)
        if job.attempts >= job.max_attempts:
            self._fail(job, err)
            return
        next_run = next_run_after(job.attempts, datetime.now(UTC))
        self.repo.reschedule(job.id, next_run, err)
        self.audit.safe_log(
            event_type=AuditEventType.JOB_RETRY_SCHEDULED,
            source="worker",
            actor_id=None,
            actor_username="",
            entity_type="job",
            entity_uuid=job.ulid,
            previous_state=None,
            new_state={
                "job_type": job.job_type,
                "ulid": job.ulid,
                "attempts": job.attempts,
                "next_run_after": next_run.isoformat(),
                "error": err,
            },
        )
        logger.info("job_retry_scheduled", ulid=job.ulid, attempts=job.attempts, next_run_after=next_run.isoformat())
