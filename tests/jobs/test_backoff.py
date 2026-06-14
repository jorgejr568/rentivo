from datetime import UTC, datetime

from rentivo.jobs.backoff import BACKOFF_SECONDS, backoff_seconds, next_run_after


def test_backoff_table_is_the_canonical_schedule():
    assert BACKOFF_SECONDS == (60, 300, 900, 3600, 21600)


def test_backoff_seconds_clamps_and_is_one_indexed():
    assert backoff_seconds(1) == 60
    assert backoff_seconds(2) == 300
    assert backoff_seconds(5) == 21600
    assert backoff_seconds(99) == 21600  # clamps to last
    assert backoff_seconds(0) == 60  # floors to first


def test_next_run_after_adds_backoff():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    out = next_run_after(1, now)
    assert (out - now).total_seconds() == 60
