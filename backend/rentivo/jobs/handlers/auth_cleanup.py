from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection, bindparam, text

from rentivo.db import get_engine
from rentivo.jobs.base import PermanentJobError
from rentivo.jobs.registry import register

AUTH_CLEANUP_BATCH_SIZE = 100

_EXPIRED_LOGIN_IDS = text(
    "SELECT id FROM api_keys WHERE is_login_token = 1 AND expires_at <= :cutoff ORDER BY id LIMIT :limit"
)
_DELETE_EXPIRED_LOGINS = text(
    "DELETE FROM api_keys WHERE id IN :ids AND is_login_token = 1 AND expires_at <= :cutoff"
).bindparams(bindparam("ids", expanding=True))
_STALE_CHALLENGE_IDS = text(
    "SELECT id FROM auth_challenges WHERE expires_at <= :cutoff OR consumed_at IS NOT NULL ORDER BY id LIMIT :limit"
)
_DELETE_STALE_CHALLENGES = text(
    "DELETE FROM auth_challenges WHERE id IN :ids AND (expires_at <= :cutoff OR consumed_at IS NOT NULL)"
).bindparams(bindparam("ids", expanding=True))


def _parse_cutoff(payload: dict) -> datetime:
    raw = payload.get("now")
    if raw is None:
        return datetime.now(UTC)
    if not isinstance(raw, str):
        raise PermanentJobError("auth.cleanup now must be an RFC 3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PermanentJobError("auth.cleanup now must be an RFC 3339 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PermanentJobError("auth.cleanup now must be an RFC 3339 UTC timestamp")
    return parsed.astimezone(UTC)


def _delete_expired_logins(connection: Connection, cutoff: datetime, limit: int) -> int:
    ids = list(
        connection.execute(
            _EXPIRED_LOGIN_IDS,
            {"cutoff": cutoff, "limit": limit},
        ).scalars()
    )
    if not ids:
        return 0
    result = connection.execute(
        _DELETE_EXPIRED_LOGINS,
        {"ids": ids, "cutoff": cutoff},
    )
    return result.rowcount


def _delete_stale_challenges(connection: Connection, cutoff: datetime, limit: int) -> int:
    ids = list(
        connection.execute(
            _STALE_CHALLENGE_IDS,
            {"cutoff": cutoff, "limit": limit},
        ).scalars()
    )
    if not ids:
        return 0
    result = connection.execute(
        _DELETE_STALE_CHALLENGES,
        {"ids": ids, "cutoff": cutoff},
    )
    return result.rowcount


@register("auth.cleanup")
def handle_auth_cleanup(payload: dict) -> dict[str, int]:
    cutoff = _parse_cutoff(payload).replace(tzinfo=None)
    with get_engine().begin() as connection:
        login_tokens_deleted = _delete_expired_logins(
            connection,
            cutoff,
            AUTH_CLEANUP_BATCH_SIZE,
        )
        challenges_deleted = _delete_stale_challenges(
            connection,
            cutoff,
            AUTH_CLEANUP_BATCH_SIZE,
        )
    return {
        "login_tokens_deleted": login_tokens_deleted,
        "challenges_deleted": challenges_deleted,
    }
