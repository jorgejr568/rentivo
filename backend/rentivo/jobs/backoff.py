from __future__ import annotations

from datetime import datetime, timedelta

# Exponential-ish retry schedule shared by the database polling worker and the
# Temporal workflow retry loop. Index 0 is the wait after attempt 1, etc.
BACKOFF_SECONDS: tuple[int, ...] = (60, 300, 900, 3600, 21600)


def backoff_seconds(attempt: int) -> int:
    """Seconds to wait before retrying after ``attempt`` (1-indexed). Clamped."""
    idx = min(max(attempt, 1) - 1, len(BACKOFF_SECONDS) - 1)
    return BACKOFF_SECONDS[idx]


def next_run_after(attempts: int, now: datetime) -> datetime:
    return now + timedelta(seconds=backoff_seconds(attempts))
