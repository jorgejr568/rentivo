from datetime import date

from rentivo.models.bill import BillStatus, BillSummary
from rentivo.services.billing_stats_service import BillingStatsService


class FakeBillRepo:
    def __init__(self, summaries):
        self._summaries = summaries

    def list_summaries(self, billing_ids):
        return [s for s in self._summaries if s.billing_id in billing_ids]


class FakeExpenseRepo:
    def __init__(self, total):
        self._total = total
        self.seen = None

    def total_for_billings(self, billing_ids):
        self.seen = list(billing_ids)
        return self._total


def test_net_income_is_received_minus_expenses():
    summaries = [
        BillSummary(billing_id=1, total_amount=1000, status=BillStatus.PAID.value, reference_month="2026-02"),
        BillSummary(billing_id=1, total_amount=500, status=BillStatus.DRAFT.value, reference_month="2026-03"),
    ]
    expense_repo = FakeExpenseRepo(total=300)
    svc = BillingStatsService(FakeBillRepo(summaries), expense_repo, cache=None)
    stats = svc.stats_for_ids([1], today=date(2026, 3, 15))
    assert stats.received == 1000
    assert stats.total_expenses == 300
    assert stats.net_income == 700
    assert expense_repo.seen == [1]


def test_empty_ids_short_circuits_no_expense_query():
    expense_repo = FakeExpenseRepo(total=999)
    svc = BillingStatsService(FakeBillRepo([]), expense_repo, cache=None)
    stats = svc.stats_for_ids([], today=date(2026, 3, 15))
    assert stats.total_expenses == 0
    assert stats.net_income == 0
    assert expense_repo.seen is None  # not queried


def test_cache_roundtrip_preserves_net_income():
    from rentivo.cache.memory import MemoryCache  # in-process cache

    summaries = [BillSummary(billing_id=1, total_amount=1000, status=BillStatus.PAID.value, reference_month="2026-02")]
    cache = MemoryCache(ttl_seconds=60, max_entries=10)
    svc = BillingStatsService(FakeBillRepo(summaries), FakeExpenseRepo(total=300), cache=cache)
    first = svc.stats_for_ids([1], today=date(2026, 3, 15))
    # second call hits cache (expense repo would re-run but value must match)
    second = svc.stats_for_ids([1], today=date(2026, 3, 15))
    assert first.net_income == second.net_income == 700
    cache.close()
