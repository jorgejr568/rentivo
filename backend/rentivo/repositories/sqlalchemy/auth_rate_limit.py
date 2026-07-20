from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import Connection, text

from rentivo.observability import traced
from rentivo.repositories.base import AuthRateLimitRepository

logger = structlog.get_logger(__name__)


def _storage_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


class SQLAlchemyAuthRateLimitRepository(AuthRateLimitRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def _reserve_once(
        self,
        *,
        action: str,
        identity_hash: bytes,
        limit: int,
        window_seconds: int,
        now: datetime,
    ) -> bool:
        stored_now = _storage_time(now)
        expires_at = stored_now + timedelta(seconds=window_seconds)
        if self.conn.dialect.name == "sqlite":
            upsert = text(
                "INSERT INTO auth_rate_limits "
                "(action, identity_hash, attempts, window_started_at, expires_at) "
                "VALUES (:action, :identity_hash, 1, :now, :expires_at) "
                "ON CONFLICT(action, identity_hash) DO UPDATE SET "
                "attempts = CASE WHEN expires_at <= :now THEN 1 "
                "ELSE MIN(attempts + 1, :blocked_attempts) END, "
                "window_started_at = CASE WHEN expires_at <= :now THEN :now "
                "ELSE window_started_at END, "
                "expires_at = CASE WHEN expires_at <= :now THEN :expires_at ELSE expires_at END"
            )
        else:  # pragma: no cover - exercised by the opt-in real MariaDB concurrency test
            upsert = text(
                "INSERT INTO auth_rate_limits "
                "(action, identity_hash, attempts, window_started_at, expires_at) "
                "VALUES (:action, :identity_hash, 1, :now, :expires_at) "
                "ON DUPLICATE KEY UPDATE "
                "attempts = IF(expires_at <= :now, 1, LEAST(attempts + 1, :blocked_attempts)), "
                "window_started_at = IF(expires_at <= :now, :now, window_started_at), "
                "expires_at = IF(expires_at <= :now, :expires_at, expires_at)"
            )
        self.conn.execute(
            upsert,
            {
                "action": action,
                "identity_hash": identity_hash,
                "now": stored_now,
                "expires_at": expires_at,
                "blocked_attempts": limit + 1,
            },
        )
        attempts = self.conn.execute(
            text("SELECT attempts FROM auth_rate_limits WHERE action = :action AND identity_hash = :identity_hash"),
            {"action": action, "identity_hash": identity_hash},
        ).scalar_one()
        self.conn.commit()
        allowed = int(attempts) <= limit
        try:
            self.delete_expired(cutoff=stored_now, limit=100)
        except Exception:
            logger.warning("auth_rate_limit_cleanup_failed")
        return allowed

    @traced("auth_rate_limit_repo.reserve", record_exception_details=False)
    def reserve(
        self,
        *,
        action: str,
        identity_hash: bytes,
        limit: int,
        window_seconds: int,
        now: datetime,
    ) -> bool:
        try:
            return self._reserve_once(
                action=action,
                identity_hash=identity_hash,
                limit=limit,
                window_seconds=window_seconds,
                now=now,
            )
        except BaseException:
            self.conn.rollback()
            raise

    @traced("auth_rate_limit_repo.clear", record_exception_details=False)
    def clear(self, *, action: str, identity_hash: bytes) -> None:
        try:
            self.conn.execute(
                text("DELETE FROM auth_rate_limits WHERE action = :action AND identity_hash = :identity_hash"),
                {"action": action, "identity_hash": identity_hash},
            )
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    @traced("auth_rate_limit_repo.delete_expired", record_exception_details=False)
    def delete_expired(self, *, cutoff: datetime, limit: int) -> int:
        try:
            result = self.conn.execute(
                text(
                    "DELETE FROM auth_rate_limits WHERE (action, identity_hash) IN ("
                    "SELECT action, identity_hash FROM ("
                    "SELECT action, identity_hash FROM auth_rate_limits "
                    "WHERE expires_at <= :cutoff ORDER BY expires_at LIMIT :limit"
                    ") AS expired_rows)"
                ),
                {"cutoff": _storage_time(cutoff), "limit": limit},
            )
            self.conn.commit()
            return result.rowcount
        except BaseException:
            self.conn.rollback()
            raise
