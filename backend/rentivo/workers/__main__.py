"""Worker entrypoint — runs the configured job driver.

Run with: ``python -m rentivo.workers``

Dispatches on ``RENTIVO_JOB_BACKEND``: the ``database`` driver runs the
polling ``Worker`` over the jobs table; the ``temporal`` driver hands off to
``rentivo.jobs.temporal.runner``. Either way the registered handlers
(``email.send``, ``communication.send``, ``pdf.render``, ``recibo.render``,
``s3.delete``, ``export.generate``) plug in via the registry without touching
this file.

This module is omitted from coverage; its job is to wire production config
into the chosen driver. The ``Worker`` class and the Temporal runner are
fully unit-tested (see tests/jobs/test_worker.py and tests/jobs/temporal/).
"""

from __future__ import annotations

import structlog

from rentivo.db import get_engine
from rentivo.jobs import handlers  # noqa: F401 — registers handlers
from rentivo.jobs.sqlalchemy import SQLAlchemyJobRepository
from rentivo.jobs.worker import Worker
from rentivo.logging import configure_logging
from rentivo.observability import configure_tracing
from rentivo.repositories.sqlalchemy import SQLAlchemyAuditLogRepository
from rentivo.services.audit_service import AuditService
from rentivo.settings import settings

logger = structlog.get_logger(__name__)


def main() -> None:
    configure_logging()
    configure_tracing()
    if settings.job_backend == "temporal":
        from rentivo.jobs.temporal.runner import run_temporal_worker

        logger.info("worker_boot", driver="temporal", task_queue=settings.temporal_task_queue)
        run_temporal_worker()
        return

    logger.info(
        "worker_boot",
        driver="database",
        batch_size=settings.job_worker_batch_size,
        idle_sleep_seconds=settings.job_worker_idle_sleep_seconds,
        stuck_after_seconds=settings.job_worker_stuck_after_seconds,
    )
    engine = get_engine()
    with engine.connect() as conn:
        repo = SQLAlchemyJobRepository(conn, stuck_after_seconds=settings.job_worker_stuck_after_seconds)
        audit = AuditService(SQLAlchemyAuditLogRepository(conn))
        worker = Worker(
            repo,
            audit,
            batch_size=settings.job_worker_batch_size,
            idle_sleep_seconds=settings.job_worker_idle_sleep_seconds,
        )
        worker.run_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
