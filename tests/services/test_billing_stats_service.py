"""Tests for BillingStatsService — year-to-date rollup, latest-per-billing,
status mapping, and cache interaction (using an injected memory cache)."""

from __future__ import annotations

from datetime import date

import pytest

from rentivo.cache.memory import MemoryCache
from rentivo.models.bill import BillSummary
from rentivo.services.billing_stats_service import BillingStatsService


class FakeBillRepo:
    """Minimal stand-in exposing only list_summaries, with a call counter."""

    def __init__(self, summaries: list[BillSummary]):
        self._summaries = summaries
        self.calls = 0

    def list_summaries(self, billing_ids):
        self.calls += 1
        # Mimic the real ordering: newest reference_month first per billing.
        return [
            s
            for s in sorted(self._summaries, key=lambda s: (s.billing_id, s.reference_month), reverse=True)
            if s.billing_id in billing_ids
        ]


def _summary(billing_id, total, status, month="2026-05"):
    return BillSummary(billing_id=billing_id, total_amount=total, status=status, reference_month=month)


TODAY = date(2026, 5, 15)


@pytest.fixture()
def cache():
    c = MemoryCache(ttl_seconds=60, max_entries=64, enable_cleanup_thread=False)
    yield c
    c.close()


class TestRollup:
    def test_empty_ids_returns_zeroed_stats_without_querying(self, cache):
        repo = FakeBillRepo([])
        stats = BillingStatsService(repo, cache).stats_for_ids([], today=TODAY)
        assert (stats.expected, stats.received, stats.pending, stats.overdue) == (0, 0, 0, 0)
        assert stats.year == 2026
        assert stats.current == {}
        assert repo.calls == 0

    def test_status_buckets_and_expected_total(self, cache):
        repo = FakeBillRepo(
            [
                _summary(1, 100000, "paid"),
                _summary(2, 200000, "sent"),
                _summary(3, 50000, "draft"),
                _summary(4, 300000, "delayed_payment"),
                _summary(5, 999999, "cancelled"),  # excluded entirely
            ]
        )
        stats = BillingStatsService(repo, cache).stats_for_ids([1, 2, 3, 4, 5], today=TODAY)

        assert stats.received == 100000
        assert stats.pending == 250000  # sent + draft
        assert stats.overdue == 300000
        assert stats.expected == 650000  # received + pending + overdue, cancelled excluded
        assert stats.paid_count == 1
        assert stats.pending_count == 2
        assert stats.overdue_count == 1
        assert stats.active_count == 3
        assert stats.billed_count == 4  # excludes cancelled
        assert set(stats.current) == {1, 2, 3, 4, 5}  # latest bill still shown per billing


class TestYearToDate:
    def test_sums_every_bill_in_the_current_year(self, cache):
        repo = FakeBillRepo(
            [
                _summary(1, 300000, "paid", "2026-02"),
                _summary(1, 358800, "paid", "2026-04"),
                _summary(1, 360400, "sent", "2026-05"),
            ]
        )
        stats = BillingStatsService(repo, cache).stats_for_ids([1], today=TODAY)

        assert stats.received == 658800  # the two paid bills
        assert stats.pending == 360400  # the sent one
        assert stats.expected == 1019200
        assert stats.paid_count == 2
        assert stats.pending_count == 1
        assert stats.current[1].reference_month == "2026-05"  # table shows latest

    def test_excludes_other_years(self, cache):
        repo = FakeBillRepo(
            [
                _summary(1, 500000, "paid", "2025-12"),  # prior year — excluded from YTD
                _summary(1, 100000, "paid", "2026-03"),
            ]
        )
        stats = BillingStatsService(repo, cache).stats_for_ids([1], today=TODAY)
        assert stats.received == 100000
        assert stats.expected == 100000
        assert stats.current[1].reference_month == "2026-03"

    def test_excludes_future_months_in_the_same_year(self, cache):
        repo = FakeBillRepo(
            [
                _summary(1, 100000, "paid", "2026-03"),
                _summary(1, 700000, "draft", "2026-09"),  # after today's month — excluded
            ]
        )
        stats = BillingStatsService(repo, cache).stats_for_ids([1], today=TODAY)
        assert stats.expected == 100000
        assert stats.pending == 0


class TestCacheInteraction:
    def test_second_call_is_served_from_cache(self, cache):
        repo = FakeBillRepo([_summary(1, 100000, "paid")])
        svc = BillingStatsService(repo, cache)

        first = svc.stats_for_ids([1], today=TODAY)
        second = svc.stats_for_ids([1], today=TODAY)

        assert repo.calls == 1  # second call served from cache
        assert first == second

    def test_clearing_cache_forces_recompute(self, cache):
        repo = FakeBillRepo([_summary(1, 100000, "paid")])
        svc = BillingStatsService(repo, cache)

        svc.stats_for_ids([1], today=TODAY)
        cache.clear()
        svc.stats_for_ids([1], today=TODAY)

        assert repo.calls == 2

    def test_cache_key_includes_the_ytd_window(self, cache):
        repo = FakeBillRepo([_summary(1, 100000, "paid")])
        svc = BillingStatsService(repo, cache)

        svc.stats_for_ids([1], today=date(2026, 5, 15))
        svc.stats_for_ids([1], today=date(2026, 6, 1))  # different month → recompute

        assert repo.calls == 2

    def test_cache_key_is_order_independent_and_deduped(self, cache):
        repo = FakeBillRepo([_summary(1, 100000, "paid"), _summary(2, 200000, "sent")])
        svc = BillingStatsService(repo, cache)

        svc.stats_for_ids([1, 2], today=TODAY)
        svc.stats_for_ids([2, 1, 1], today=TODAY)  # same set, different order + duplicate

        assert repo.calls == 1

    def test_none_ids_are_dropped(self, cache):
        repo = FakeBillRepo([_summary(1, 100000, "paid")])
        svc = BillingStatsService(repo, cache)
        stats = svc.stats_for_ids([1, None], today=TODAY)
        assert stats.expected == 100000
        assert repo.calls == 1
