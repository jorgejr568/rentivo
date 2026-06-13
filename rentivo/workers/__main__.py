"""Worker entrypoint — drains the jobs table.

Run with: ``python -m rentivo.workers``

The worker is generic and dispatches any registered handler (currently
just ``email.send``; future handlers like ``pdf.render`` plug in via the
registry without touching this file).

This module is omitted from coverage; its job is to wire the production
DB connection into the Worker loop. The Worker class itself is fully
unit-tested (see tests/jobs/test_worker.py).
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
    logger.info(
        "worker_boot",
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
