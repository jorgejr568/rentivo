from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable

import structlog
from ulid import ULID

from rentivo.jobs.backend import JobBackend
from rentivo.jobs.base import Job
from rentivo.jobs.temporal.client import AsyncBridge, build_client
from rentivo.jobs.temporal.config import TemporalConfig, config_from_settings
from rentivo.jobs.temporal.workflows import (
    CommunicationSendWorkflow,
    EmailSendWorkflow,
    PdfRenderWorkflow,
    S3DeleteWorkflow,
)

logger = structlog.get_logger(__name__)

_WORKFLOW_BY_TYPE = {
    "email.send": EmailSendWorkflow,
    "communication.send": CommunicationSendWorkflow,
    "pdf.render": PdfRenderWorkflow,
    "s3.delete": S3DeleteWorkflow,
}


class TemporalJobBackend(JobBackend):
    """Enqueue a job by starting one Temporal workflow per call.

    The workflow id is ``job-<ulid>`` (idempotency / dedup key). ``run_after``
    maps to Temporal's ``start_delay``.
    """

    def __init__(
        self,
        cfg: TemporalConfig,
        *,
        bridge: AsyncBridge | None = None,
        connect: Callable[[TemporalConfig], object] | None = None,
    ) -> None:
        self._cfg = cfg
        self._bridge = bridge or AsyncBridge()
        self._connect = connect or build_client
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            self._client = self._bridge.run(self._connect(self._cfg))
        return self._client

    def enqueue(
        self,
        job_type: str,
        payload: dict,
        run_after: datetime | None = None,
        max_attempts: int = 5,
    ) -> Job:
        wf = _WORKFLOW_BY_TYPE.get(job_type)
        if wf is None:
            raise ValueError(f"no Temporal workflow registered for job_type {job_type!r}")
        ulid = str(ULID())
        client = self._ensure_client()
        start_delay = _start_delay(run_after)
        self._bridge.run(
            client.start_workflow(
                wf.run,
                args=[payload, ulid, max_attempts],
                id=f"job-{ulid}",
                task_queue=self._cfg.task_queue,
                start_delay=start_delay,
            )
        )
        logger.info("job_enqueued_temporal", job_type=job_type, ulid=ulid)
        return Job(
            id=0,  # not meaningful for the Temporal backend; callers read only .ulid
            ulid=ulid,
            job_type=job_type,
            payload=payload,
            attempts=0,
            max_attempts=max_attempts,
        )


def _start_delay(run_after: datetime | None) -> timedelta | None:
    if run_after is None:
        return None
    delta = run_after - datetime.now(UTC)
    return delta if delta.total_seconds() > 0 else None


_singleton: TemporalJobBackend | None = None


def build_temporal_backend() -> TemporalJobBackend:
    """Process-global Temporal backend (one client/bridge per process)."""
    global _singleton
    if _singleton is None:
        _singleton = TemporalJobBackend(config_from_settings())
    return _singleton
