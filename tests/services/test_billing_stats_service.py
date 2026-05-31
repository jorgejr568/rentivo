"""Tests for BillingStatsService — rollup logic, status mapping, and the
process-global TTL cache."""

from __future__ import annotations

import pytest

from rentivo.models.bill import BillSummary
from rentivo.services.billing_stats_service import BillingStatsService, clear_cache


class FakeBillRepo:
    """Minimal stand-in exposing only current_summaries, with a call counter."""

    def __init__(self, summaries: dict[int, BillSummary]):
        self._summaries = summaries
        self.calls = 0

    def current_summaries(self, billing_ids):
        self.calls += 1
        return {bid: s for bid, s in self._summaries.items() if bid in billing_ids}


def _summary(billing_id, total, status):
    return BillSummary(billing_id=billing_id, total_amount=total, status=status, reference_month="2026-05")


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


class TestRollup:
    def test_empty_ids_returns_zeroed_stats_without_querying(self):
        repo = FakeBillRepo({})
        stats = BillingStatsService(repo).stats_for_ids([])
        assert (stats.expected, stats.received, stats.pending, stats.overdue) == (0, 0, 0, 0)
        assert stats.current == {}
        assert repo.calls == 0

    def test_status_buckets_and_expected_total(self):
        repo = FakeBillRepo(
            {
                1: _summary(1, 100000, "paid"),
                2: _summary(2, 200000, "sent"),
                3: _summary(3, 50000, "draft"),
                4: _summary(4, 300000, "delayed_payment"),
                5: _summary(5, 999999, "cancelled"),  # excluded entirely
            }
        )
        stats = BillingStatsService(repo).stats_for_ids([1, 2, 3, 4, 5])

        assert stats.received == 100000
        assert stats.pending == 250000  # sent + draft
        assert stats.overdue == 300000
        assert stats.expected == 650000  # received + pending + overdue, cancelled excluded
        assert stats.paid_count == 1
        assert stats.pending_count == 2
        assert stats.overdue_count == 1
        assert stats.active_count == 3
        assert set(stats.current) == {1, 2, 3, 4, 5}  # cancelled still shown in the table

    def test_billing_without_a_bill_contributes_nothing(self):
        repo = FakeBillRepo({1: _summary(1, 100000, "paid")})
        stats = BillingStatsService(repo).stats_for_ids([1, 2])
        assert stats.expected == 100000
        assert 2 not in stats.current


class TestCache:
    def test_second_call_is_served_from_cache(self):
        repo = FakeBillRepo({1: _summary(1, 100000, "paid")})
        svc = BillingStatsService(repo)

        first = svc.stats_for_ids([1])
        second = svc.stats_for_ids([1])

        assert repo.calls == 1
        assert first is second

    def test_clear_cache_forces_recompute(self):
        repo = FakeBillRepo({1: _summary(1, 100000, "paid")})
        svc = BillingStatsService(repo)

        svc.stats_for_ids([1])
        clear_cache()
        svc.stats_for_ids([1])

        assert repo.calls == 2

    def test_cache_key_is_order_independent_and_deduped(self):
        repo = FakeBillRepo({1: _summary(1, 100000, "paid"), 2: _summary(2, 200000, "sent")})
        svc = BillingStatsService(repo)

        svc.stats_for_ids([1, 2])
        svc.stats_for_ids([2, 1, 1])  # same set, different order + duplicate

        assert repo.calls == 1

    def test_none_ids_are_dropped(self):
        repo = FakeBillRepo({1: _summary(1, 100000, "paid")})
        svc = BillingStatsService(repo)
        stats = svc.stats_for_ids([1, None])
        assert stats.expected == 100000
        assert repo.calls == 1
