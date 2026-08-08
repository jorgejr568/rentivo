from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import Connection, bindparam, text
from ulid import ULID

from rentivo.constants import SP_TZ
from rentivo.encryption.base import EncryptionBackend
from rentivo.jobs.base import Job, JobRepository

logger = structlog.get_logger(__name__)

_ENVELOPE_KEY = "__enc"


def _now() -> datetime:
    return datetime.now(SP_TZ).replace(tzinfo=None)


def _to_naive_sp(dt: datetime) -> datetime:
    """Normalise a datetime to naive SP_TZ wall-clock (the storage convention).

    Naive inputs are assumed to already be SP_TZ and pass through unchanged;
    aware inputs are converted to SP_TZ before the tzinfo is dropped.
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(SP_TZ).replace(tzinfo=None)


def encode_job_payload(encryption: EncryptionBackend, payload: dict) -> str:
    """Serialize ``payload`` into the encrypted at-rest envelope.

    The stored value is a JSON *object* -- ``{"__enc": "<ciphertext>"}`` -- and
    deliberately not a bare ciphertext string. MariaDB renders the
    ``jobs.payload`` column (declared ``sa.JSON`` in migration d74d94c5ff3c) as
    ``longtext ... CHECK (json_valid(payload))``, so writing ``enc:v1:...``
    directly fails with ``ERROR 4025 CONSTRAINT jobs.payload failed``. SQLite --
    which the test suite uses -- has no such constraint, so the envelope is what
    keeps local runs honest about production behaviour.
    """
    return json.dumps({_ENVELOPE_KEY: encryption.encrypt(json.dumps(payload))})


def decode_job_payload(encryption: EncryptionBackend, raw: str | dict) -> dict:
    """Parse a stored ``jobs.payload`` value, decrypting the envelope if present.

    Three shapes are accepted so encrypted and legacy rows coexist without a
    flag day (the same coexistence contract ``EncryptionBackend`` documents):

    - ``{"__enc": "<ciphertext>"}``  -> decrypt, then parse the plaintext JSON
    - ``{...}``                      -> a legacy plaintext row; returned as-is
    - a ``dict``                     -> already parsed by the driver; as above

    No producer emits a ``__enc`` key, so its presence is an unambiguous marker.
    """
    decoded = raw if isinstance(raw, dict) else json.loads(raw)
    if isinstance(decoded, dict) and _ENVELOPE_KEY in decoded:
        return json.loads(encryption.decrypt(decoded[_ENVELOPE_KEY]))
    return decoded


class SQLAlchemyJobRepository(JobRepository):
    def __init__(
        self,
        conn: Connection,
        encryption: EncryptionBackend,
        *,
        stuck_after_seconds: int = 600,
    ) -> None:
        self.conn = conn
        self.encryption = encryption
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
        run_at = now if run_after is None else _to_naive_sp(run_after)
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
                "payload": encode_job_payload(self.encryption, payload),
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

    def _decode_rows(self, rows: Sequence[Mapping]) -> list[tuple[Mapping, dict]]:
        """Pair each row with its decoded payload, dropping rows that fail.

        A row is skipped rather than dead-lettered: a transient decrypt failure
        (KMS unavailable) must never silently discard queued work. A row that is
        permanently undecryptable is skipped on every poll and logged, so it
        stalls loudly instead of blocking every other job behind it in the
        ``ORDER BY id`` scan.
        """
        decoded: list[tuple[Mapping, dict]] = []
        for row in rows:
            try:
                payload = decode_job_payload(self.encryption, row["payload"])
            except Exception:
                logger.exception(
                    "job_payload_decode_failed",
                    job_id=row["id"],
                    ulid=row["ulid"],
                )
                continue
            decoded.append((row, payload))
        return decoded

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
        # Decode BEFORE the claiming UPDATE. Decoding afterwards would burn an
        # attempt and crash the worker out of tick() with the job stuck in
        # 'running' until the stuck-reclaim window elapsed -- and because
        # Worker._reschedule_or_fail would never run, max_attempts would never
        # dead-letter it. Rolling back here leaves every row 'pending' with its
        # attempt count untouched, so a KMS outage is fully self-healing.
        claimable = self._decode_rows(rows)
        if not claimable:
            self.conn.rollback()
            return []
        ids = [row["id"] for row, _ in claimable]
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
                payload=payload,
                attempts=row["attempts"] + 1,
                max_attempts=row["max_attempts"],
            )
            for row, payload in claimable
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
        run_at = _to_naive_sp(run_after)
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

    def has_active_or_recent(self, job_type: str, within_seconds: int) -> bool:
        """True when a `job_type` job is queued, running, or finished recently.

        The worker's periodic scheduling uses this to avoid piling up duplicates:
        an active row means one is already due, and a terminal row touched inside
        the window means the last run is still recent enough. The cutoff is
        computed here rather than with `NOW() - INTERVAL`, so the statement stays
        portable and testable on SQLite.

        The cutoff is naive **UTC**, not `_now()`: a terminal row's `updated_at`
        is written by the database server clock (SQL `NOW()`), assumed UTC on the
        production database (stock mariadb:11) -- the same assumption the
        retention purge in the `auth.cleanup` handler documents. Comparing those
        timestamps against app-local Sao Paulo wall-clock would push the cutoff
        three hours into the past and keep a finished run "recent" for the window
        plus the UTC offset. `pending`/`running` rows are matched by the status
        clause regardless of their timestamp, so the `_now()` values written for
        them do not take part in this comparison.
        """
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=within_seconds)
        row = self.conn.execute(
            text(
                "SELECT 1 FROM jobs "
                "WHERE job_type = :job_type "
                "AND (status IN ('pending', 'running') OR updated_at > :cutoff) "
                "LIMIT 1"
            ),
            {"job_type": job_type, "cutoff": cutoff},
        ).scalar()
        self.conn.commit()
        return row is not None
