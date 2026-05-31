"""Shared fixtures + factory isolation for stats-cache tests."""

from __future__ import annotations

import pytest

from rentivo.models.bill import BillSummary
from rentivo.services.billing_stats import BillingStats


@pytest.fixture(autouse=True)
def _reset_stats_cache_factory():
    """Close and drop the module-level cache between tests so monkeypatched
    settings take effect and background threads from a prior test are joined."""
    from rentivo.services.stats_cache import factory as factory_module

    factory_module._reset_for_tests()
    yield
    factory_module._reset_for_tests()


@pytest.fixture()
def sample_stats() -> BillingStats:
    return BillingStats(
        year=2026,
        expected=460400,
        received=100000,
        pending=360400,
        overdue=0,
        paid_count=1,
        pending_count=1,
        overdue_count=0,
        current={
            1: BillSummary(billing_id=1, total_amount=360400, status="sent", reference_month="2026-05"),
        },
    )
