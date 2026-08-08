from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class JobContext:
    """Per-run job identity handed to every handler alongside its payload.

    ``ulid`` is the durable identity of the job (the queue row's ULID on the
    database backend, the workflow id's ULID suffix on Temporal), so it is
    stable across retries of the same job and usable as an operation token.
    ``attempts`` is the 1-based number of the attempt now running.
    """

    ulid: str
    attempts: int


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

    @abstractmethod
    def count_by_type_and_statuses(
        self,
        job_type: str,
        statuses: Sequence[str],
    ) -> int: ...

    @abstractmethod
    def has_active_or_recent(self, job_type: str, within_seconds: int) -> bool: ...


class PermanentJobError(Exception):
    """Handler raises this to skip retries and dead-letter the job immediately."""
