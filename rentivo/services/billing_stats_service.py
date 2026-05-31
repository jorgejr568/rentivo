"""Dashboard / organization KPI rollups computed from the latest bill per billing.

The billings list and organization detail pages show four money KPIs
(a receber · mês / recebido / pendente / em atraso) plus the current-bill
status per property. Those numbers come from the *latest* bill of each billing.

Because the read happens on hot navigation paths, the per-billing-set result is
memoised in a process-global TTL cache (default 60s). Staleness is bounded by
the TTL: a status change is reflected within a minute. The cache is keyed by the
exact set of billing ids, so it is shared across users without leaking data
(bill ids are globally unique and the underlying rows are identical regardless
of who reads them).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

from cachetools import TTLCache

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
    """Monthly rollup across a set of billings, plus each billing's current bill.

    All money values are in centavos. ``current`` maps ``billing_id`` to the
    latest :class:`BillSummary` (including cancelled bills, so the table can
    still render their status); billings without any bill are absent.
    """

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


def _compute(summaries: dict[int, BillSummary]) -> BillingStats:
    expected = received = pending = overdue = 0
    paid_count = pending_count = overdue_count = 0
    for summary in summaries.values():
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
    return BillingStats(
        expected=expected,
        received=received,
        pending=pending,
        overdue=overdue,
        paid_count=paid_count,
        pending_count=pending_count,
        overdue_count=overdue_count,
        current=summaries,
    )


class BillingStatsService:
    def __init__(self, bill_repo: BillRepository) -> None:
        self._bill_repo = bill_repo

    def stats_for_ids(self, billing_ids: list[int]) -> BillingStats:
        ids = tuple(sorted({bid for bid in billing_ids if bid is not None}))
        if not ids:
            return BillingStats()
        with _LOCK:
            cached = _CACHE.get(ids)
            if cached is not None:
                return cached
        summaries = self._bill_repo.current_summaries(list(ids))
        stats = _compute(summaries)
        with _LOCK:
            _CACHE[ids] = stats
        return stats
