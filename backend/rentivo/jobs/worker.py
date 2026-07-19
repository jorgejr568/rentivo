from __future__ import annotations

import os
import signal
import socket
import time
from datetime import UTC, datetime

import structlog

from rentivo.jobs import registry
from rentivo.jobs.backoff import BACKOFF_SECONDS as _BACKOFF_SECONDS  # noqa: F401
from rentivo.jobs.backoff import next_run_after
from rentivo.jobs.base import Job, JobRepository, PermanentJobError
from rentivo.models.audit_log import AuditEventType
from rentivo.observability import extract_context, span, suppress_tracing
from rentivo.services.audit_service import AuditService

logger = structlog.get_logger(__name__)

__all__ = ["Worker", "next_run_after"]

_MAX_ERROR_LEN = 4096
_OWNED_RENDER_JOB_TYPES = frozenset({"pdf.render", "recibo.render"})


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
        # The poll fires every few seconds even when idle; don't trace its query.
        with suppress_tracing():
            jobs = self.repo.claim_batch(self.batch_size, self.worker_id)
        for job in jobs:
            self._run_one(job)
        return len(jobs)

    def _audit_job(self, job: Job, event_type: AuditEventType, new_state: dict) -> None:
        self.audit.safe_log(
            event_type=event_type,
            source="worker",
            actor_id=None,
            actor_username="",
            entity_type="job",
            entity_uuid=job.ulid,
            previous_state=None,
            new_state=new_state,
        )

    def _run_one(self, job: Job) -> None:
        handler = registry.get(job.job_type)
        if handler is None:
            self._fail(job, f"no handler registered for job_type {job.job_type!r}")
            return
        parent = extract_context(job.payload.get("_otel", {}))
        attributes = {"job.type": job.job_type, "job.ulid": job.ulid, "job.attempts": job.attempts}
        try:
            with span(f"job {job.job_type}", parent=parent, attributes=attributes):
                payload = job.payload
                if job.job_type in _OWNED_RENDER_JOB_TYPES:
                    payload = {**payload, "_job_ulid": job.ulid}
                handler(payload)
        except PermanentJobError as exc:
            self._fail(job, str(exc))
        except Exception as exc:
            self._reschedule_or_fail(job, exc)
        else:
            self.repo.mark_succeeded(job.id)
            self._audit_job(
                job,
                AuditEventType.JOB_SUCCEEDED,
                {"job_type": job.job_type, "ulid": job.ulid, "attempts": job.attempts},
            )
            logger.info("job_succeeded", ulid=job.ulid, attempts=job.attempts)

    def _fail(self, job: Job, err: str) -> None:
        err = _truncate(err, _MAX_ERROR_LEN)
        self.repo.mark_failed(job.id, err)
        self._audit_job(
            job,
            AuditEventType.JOB_FAILED,
            {"job_type": job.job_type, "ulid": job.ulid, "attempts": job.attempts, "error": err},
        )
        hook = registry.get_fail_hook(job.job_type)
        if hook is not None:
            try:
                hook(job.payload)
            except Exception:
                logger.exception("job_fail_hook_failed", ulid=job.ulid, job_type=job.job_type)
        logger.warning("job_failed", ulid=job.ulid, attempts=job.attempts, error=err)

    def _reschedule_or_fail(self, job: Job, exc: Exception) -> None:
        err = _truncate(repr(exc), _MAX_ERROR_LEN)
        if job.attempts >= job.max_attempts:
            self._fail(job, err)
            return
        next_run = next_run_after(job.attempts, datetime.now(UTC))
        self.repo.reschedule(job.id, next_run, err)
        self._audit_job(
            job,
            AuditEventType.JOB_RETRY_SCHEDULED,
            {
                "job_type": job.job_type,
                "ulid": job.ulid,
                "attempts": job.attempts,
                "next_run_after": next_run.isoformat(),
                "error": err,
            },
        )
        logger.info("job_retry_scheduled", ulid=job.ulid, attempts=job.attempts, next_run_after=next_run.isoformat())
