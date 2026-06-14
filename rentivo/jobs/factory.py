from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from rentivo.jobs.backend import DatabaseJobBackend, JobBackend
from rentivo.settings import settings

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

logger = structlog.get_logger(__name__)


def get_job_backend(conn: "Connection") -> JobBackend:
    """Return the configured producer-side job backend.

    ``conn`` is the request/process-scoped DB connection used by the database
    backend. The Temporal backend ignores it (it talks to a Temporal cluster via
    a process-global client) but the parameter keeps a single call signature.
    """
    backend = settings.job_backend
    if backend == "database":
        from rentivo.jobs.sqlalchemy import SQLAlchemyJobRepository

        logger.info("job_backend_selected", backend="database")
        return DatabaseJobBackend(
            SQLAlchemyJobRepository(conn, stuck_after_seconds=settings.job_worker_stuck_after_seconds)
        )
    if backend == "temporal":
        from rentivo.jobs.temporal.backend import build_temporal_backend

        logger.info("job_backend_selected", backend="temporal")
        return build_temporal_backend()
    raise ValueError(f"Unsupported job backend: {backend}")
