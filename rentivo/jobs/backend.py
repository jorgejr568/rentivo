from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from rentivo.jobs.base import Job, JobRepository


class JobBackend(ABC):
    """Producer-side contract: how a job is *enqueued*.

    The database driver writes a ``jobs`` row; the Temporal driver starts a
    workflow. Worker-side concerns (claim/reschedule/mark) stay on
    ``JobRepository`` — only the database driver's polling worker uses those.
    """

    @abstractmethod
    def enqueue(
        self,
        job_type: str,
        payload: dict,
        run_after: datetime | None = None,
        max_attempts: int = 5,
    ) -> Job: ...


class DatabaseJobBackend(JobBackend):
    """Enqueue by inserting a row via the existing ``JobRepository``."""

    def __init__(self, repo: JobRepository) -> None:
        self.repo = repo

    def enqueue(
        self,
        job_type: str,
        payload: dict,
        run_after: datetime | None = None,
        max_attempts: int = 5,
    ) -> Job:
        return self.repo.enqueue(job_type, payload, run_after, max_attempts)
