from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Job:
    id: int
    ulid: str
    job_type: str
    payload: dict
    attempts: int
    max_attempts: int


class JobRepository(ABC):
    @abstractmethod
    def enqueue(
        self,
        job_type: str,
        payload: dict,
        run_after: datetime | None = None,
        max_attempts: int = 5,
    ) -> Job: ...

    @abstractmethod
    def claim_batch(self, batch_size: int, worker_id: str) -> list[Job]: ...

    @abstractmethod
    def mark_succeeded(self, job_id: int) -> None: ...

    @abstractmethod
    def reschedule(self, job_id: int, run_after: datetime, last_error: str) -> None: ...

    @abstractmethod
    def mark_failed(self, job_id: int, last_error: str) -> None: ...


class PermanentJobError(Exception):
    """Handler raises this to skip retries and dead-letter the job immediately."""
