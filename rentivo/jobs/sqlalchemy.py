from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Connection, bindparam, text
from ulid import ULID

from rentivo.constants import SP_TZ
from rentivo.jobs.base import Job, JobRepository


def _now() -> datetime:
    return datetime.now(SP_TZ).replace(tzinfo=None)


class SQLAlchemyJobRepository(JobRepository):
    def __init__(self, conn: Connection, *, stuck_after_seconds: int = 600) -> None:
        self.conn = conn
        self.stuck_after_seconds = stuck_after_seconds

    def enqueue(
        self,
        job_type: str,
        payload: dict,
        run_after: datetime | None = None,
        max_attempts: int = 5,
    ) -> Job:
        ulid = str(ULID())
        now = _now()
        if run_after is None:
            run_at = now
        elif run_after.tzinfo is None:
            run_at = run_after
        else:
            run_at = run_after.astimezone(SP_TZ).replace(tzinfo=None)
        result = self.conn.execute(
            text(
                "INSERT INTO jobs (ulid, job_type, payload, status, attempts, max_attempts, "
                "run_after, created_at, updated_at) "
                "VALUES (:ulid, :job_type, :payload, 'pending', 0, :max_attempts, "
                ":run_after, :now, :now)"
            ),
            {
                "ulid": ulid,
                "job_type": job_type,
                "payload": json.dumps(payload),
                "max_attempts": max_attempts,
                "run_after": run_at,
                "now": now,
            },
        )
        job_id = result.lastrowid
        self.conn.commit()
        return Job(
            id=job_id,
            ulid=ulid,
            job_type=job_type,
            payload=payload,
            attempts=0,
            max_attempts=max_attempts,
        )

    def claim_batch(self, batch_size: int, worker_id: str) -> list[Job]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT id, ulid, job_type, payload, attempts, max_attempts "
                    "FROM jobs "
                    "WHERE (status = 'pending' AND run_after <= NOW()) "
                    "   OR (status = 'running' AND claimed_at < NOW() - INTERVAL :stuck SECOND) "
                    "ORDER BY id "
                    "LIMIT :batch_size "
                    "FOR UPDATE SKIP LOCKED"
                ),
                {"stuck": self.stuck_after_seconds, "batch_size": batch_size},
            )
            .mappings()
            .all()
        )
        if not rows:
            self.conn.commit()
            return []
        ids = [row["id"] for row in rows]
        update_stmt = text(
            "UPDATE jobs SET status = 'running', claimed_at = NOW(), claimed_by = :worker_id, "
            "attempts = attempts + 1, updated_at = NOW() "
            "WHERE id IN :ids"
        ).bindparams(bindparam("ids", expanding=True))
        self.conn.execute(update_stmt, {"worker_id": worker_id, "ids": ids})
        self.conn.commit()
        return [
            Job(
                id=row["id"],
                ulid=row["ulid"],
                job_type=row["job_type"],
                payload=row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"]),
                attempts=row["attempts"] + 1,
                max_attempts=row["max_attempts"],
            )
            for row in rows
        ]

    def mark_succeeded(self, job_id: int) -> None:
        self.conn.execute(
            text(
                "UPDATE jobs SET status = 'succeeded', succeeded_at = NOW(), updated_at = NOW(), "
                "last_error = NULL "
                "WHERE id = :id"
            ),
            {"id": job_id},
        )
        self.conn.commit()

    def reschedule(self, job_id: int, run_after: datetime, last_error: str) -> None:
        run_at = run_after if run_after.tzinfo is None else run_after.astimezone(SP_TZ).replace(tzinfo=None)
        self.conn.execute(
            text(
                "UPDATE jobs SET status = 'pending', run_after = :run_after, "
                "claimed_at = NULL, claimed_by = NULL, last_error = :err, updated_at = NOW() "
                "WHERE id = :id"
            ),
            {"id": job_id, "run_after": run_at, "err": last_error},
        )
        self.conn.commit()

    def mark_failed(self, job_id: int, last_error: str) -> None:
        self.conn.execute(
            text(
                "UPDATE jobs SET status = 'failed', failed_at = NOW(), last_error = :err, "
                "updated_at = NOW() "
                "WHERE id = :id"
            ),
            {"id": job_id, "err": last_error},
        )
        self.conn.commit()

    def count_by_type_and_statuses(
        self,
        job_type: str,
        statuses: Sequence[str],
    ) -> int:
        stmt = text("SELECT COUNT(*) FROM jobs WHERE job_type = :job_type AND status IN :statuses").bindparams(
            bindparam("statuses", expanding=True)
        )
        result = self.conn.execute(stmt, {"job_type": job_type, "statuses": list(statuses)}).scalar()
        return int(result or 0)
