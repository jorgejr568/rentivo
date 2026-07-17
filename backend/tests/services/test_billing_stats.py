"""Round-trip serialisation tests for the BillingStats value object."""

from __future__ import annotations

from rentivo.models.bill import BillSummary
from rentivo.services.billing_stats import BillingStats


def _stats() -> BillingStats:
    return BillingStats(
        year=2026,
        expected=650000,
        received=100000,
        pending=250000,
        overdue=300000,
        paid_count=1,
        pending_count=2,
        overdue_count=1,
        current={
            7: BillSummary(billing_id=7, total_amount=100000, status="paid", reference_month="2026-05"),
            9: BillSummary(
                billing_id=9,
                total_amount=300000,
                status="delayed_payment",
                reference_month="2026-04",
                due_date="08/04/2026",
            ),
        },
    )


def test_derived_counts():
    stats = _stats()
    assert stats.active_count == 3  # pending + overdue
    assert stats.billed_count == 4  # paid + pending + overdue


def test_to_dict_is_json_friendly():
    data = _stats().to_dict()
    assert data["year"] == 2026
    assert data["expected"] == 650000
    # current keys are stringified for JSON object compatibility
    assert set(data["current"]) == {"7", "9"}
    assert data["current"]["9"]["status"] == "delayed_payment"


def test_round_trip_preserves_everything():
    original = _stats()
    restored = BillingStats.from_dict(original.to_dict())
    assert restored == original
    assert restored.current[9].due_date == "08/04/2026"
    assert restored.current[7].billing_id == 7
