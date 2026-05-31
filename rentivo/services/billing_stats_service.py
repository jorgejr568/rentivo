"""Dashboard / organization KPI rollups.

The billings list and organization detail pages show four money KPIs for the
current year (faturado · ano / recebido / pendente / em atraso) plus the
current-bill status per property.

- The KPI cards aggregate every bill whose ``reference_month`` falls in the
  current year, year-to-date (January through the current month, São Paulo time).
- The per-property table shows each billing's *latest* bill regardless of year.

Both are derived from a single ``list_summaries`` query. Because the read happens
on hot navigation paths, the per-(period, billing-set) result is memoised in a
process-global TTL cache (default 60s); staleness is bounded by the TTL. The
cache is keyed by the year-to-date window plus the exact set of billing ids, so
it is shared across users without leaking data (bill ids are globally unique and
the underlying rows are identical regardless of who reads them).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from threading import RLock

from cachetools import TTLCache

from rentivo.constants import SP_TZ
from rentivo.models.bill import BillStatus, BillSummary
from rentivo.repositories.base import BillRepository

# Statuses that count as already received / overdue. Everything else that is not
# cancelled is treated as "pending" (still expected this cycle).
_RECEIVED = {BillStatus.PAID.value}
_OVERDUE = {BillStatus.DELAYED_PAYMENT.value}
_EXCLUDED = {BillStatus.CANCELLED.value}

CACHE_TTL_SECONDS = 60
_CACHE: TTLCache = TTLCache(maxsize=1024, ttl=CACHE_TTL_SECONDS)
_LOCK = RLock()


def clear_cache() -> None:
    """Drop all cached stats. Used between tests and after the TTL is irrelevant."""
    with _LOCK:
        _CACHE.clear()


@dataclass(frozen=True)
class BillingStats:
    """Year-to-date rollup across a set of billings, plus each billing's current bill.

    All money values are in centavos. ``year`` is the calendar year the rollup
    covers. ``current`` maps ``billing_id`` to its latest :class:`BillSummary`
    (any year, including cancelled bills so the table can still render their
    status); billings without any bill are absent.
    """

    year: int = 0
    expected: int = 0
    received: int = 0
    pending: int = 0
    overdue: int = 0
    paid_count: int = 0
    pending_count: int = 0
    overdue_count: int = 0
    current: dict[int, BillSummary] = field(default_factory=dict)

    @property
    def active_count(self) -> int:
        return self.pending_count + self.overdue_count

    @property
    def billed_count(self) -> int:
        return self.paid_count + self.pending_count + self.overdue_count


def _latest_per_billing(summaries: list[BillSummary]) -> dict[int, BillSummary]:
    # ``summaries`` is ordered newest-first per billing, so the first seen wins.
    current: dict[int, BillSummary] = {}
    for summary in summaries:
        current.setdefault(summary.billing_id, summary)
    return current


def _ytd_rollup(summaries: list[BillSummary], year: int, month: int) -> dict[str, int]:
    lo, hi = f"{year:04d}-01", f"{year:04d}-{month:02d}"
    expected = received = pending = overdue = 0
    paid_count = pending_count = overdue_count = 0
    for summary in summaries:
        if not (lo <= summary.reference_month <= hi):
            continue
        if summary.status in _EXCLUDED:
            continue
        expected += summary.total_amount
        if summary.status in _RECEIVED:
            received += summary.total_amount
            paid_count += 1
        elif summary.status in _OVERDUE:
            overdue += summary.total_amount
            overdue_count += 1
        else:
            pending += summary.total_amount
            pending_count += 1
    return {
        "expected": expected,
        "received": received,
        "pending": pending,
        "overdue": overdue,
        "paid_count": paid_count,
        "pending_count": pending_count,
        "overdue_count": overdue_count,
    }


class BillingStatsService:
    def __init__(self, bill_repo: BillRepository) -> None:
        self._bill_repo = bill_repo

    def stats_for_ids(self, billing_ids: list[int], *, today: date | None = None) -> BillingStats:
        if today is None:
            today = datetime.now(SP_TZ).date()
        ids = tuple(sorted({bid for bid in billing_ids if bid is not None}))
        if not ids:
            return BillingStats(year=today.year)

        key = (today.year, today.month, ids)
        with _LOCK:
            cached = _CACHE.get(key)
            if cached is not None:
                return cached

        summaries = self._bill_repo.list_summaries(list(ids))
        rollup = _ytd_rollup(summaries, today.year, today.month)
        stats = BillingStats(year=today.year, current=_latest_per_billing(summaries), **rollup)

        with _LOCK:
            _CACHE[key] = stats
        return stats
