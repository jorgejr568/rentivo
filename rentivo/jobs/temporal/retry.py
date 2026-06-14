from __future__ import annotations

# Activity failures raised with this Temporal ApplicationError ``type`` are
# treated as permanent (no retry, dead-letter immediately) — the analogue of
# the database driver's ``PermanentJobError``.
PERMANENT_ERROR_TYPE = "PermanentJobError"


def is_permanent(error_type: str | None) -> bool:
    return error_type == PERMANENT_ERROR_TYPE


def should_give_up(attempt: int, max_attempts: int, permanent: bool) -> bool:
    """Mirror ``Worker._reschedule_or_fail``: give up (dead-letter) when the
    failure is permanent, or when this attempt is the last allowed one."""
    return permanent or attempt >= max_attempts
