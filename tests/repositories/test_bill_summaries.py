"""Tests for SQLAlchemyBillRepository.current_summaries — the lightweight
latest-bill-per-billing query that backs the dashboard / organization KPIs."""

from __future__ import annotations


class TestCurrentSummaries:
    def _billing(self, billing_repo, sample_billing, **overrides):
        return billing_repo.create(sample_billing(**overrides))

    def test_empty_input_returns_empty(self, bill_repo):
        assert bill_repo.current_summaries([]) == {}

    def test_billing_with_no_bills_is_omitted(self, bill_repo, billing_repo, sample_billing):
        billing = self._billing(billing_repo, sample_billing)
        assert bill_repo.current_summaries([billing.id]) == {}

    def test_returns_latest_bill_per_billing(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._billing(billing_repo, sample_billing)
        bill_repo.create(
            sample_bill(billing_id=billing.id, reference_month="2025-01", total_amount=100000, status="paid")
        )
        bill_repo.create(
            sample_bill(billing_id=billing.id, reference_month="2025-03", total_amount=300000, status="sent")
        )
        bill_repo.create(
            sample_bill(billing_id=billing.id, reference_month="2025-02", total_amount=200000, status="draft")
        )

        summaries = bill_repo.current_summaries([billing.id])

        assert set(summaries) == {billing.id}
        current = summaries[billing.id]
        assert current.reference_month == "2025-03"
        assert current.total_amount == 300000
        assert current.status == "sent"

    def test_maps_multiple_billings(self, bill_repo, billing_repo, sample_billing, sample_bill):
        a = self._billing(billing_repo, sample_billing, name="A")
        b = self._billing(billing_repo, sample_billing, name="B")
        c = self._billing(billing_repo, sample_billing, name="C")  # no bills
        bill_repo.create(
            sample_bill(billing_id=a.id, reference_month="2026-05", total_amount=351200, status="delayed_payment")
        )
        bill_repo.create(sample_bill(billing_id=b.id, reference_month="2026-05", total_amount=171500, status="paid"))

        summaries = bill_repo.current_summaries([a.id, b.id, c.id])

        assert set(summaries) == {a.id, b.id}
        assert summaries[a.id].status == "delayed_payment"
        assert summaries[a.id].due_date is not None
        assert summaries[b.id].total_amount == 171500

    def test_ignores_soft_deleted_bills(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._billing(billing_repo, sample_billing)
        bill_repo.create(
            sample_bill(billing_id=billing.id, reference_month="2025-01", total_amount=100000, status="paid")
        )
        newer = bill_repo.create(
            sample_bill(billing_id=billing.id, reference_month="2025-06", total_amount=600000, status="sent")
        )

        bill_repo.delete(newer.id)
        summaries = bill_repo.current_summaries([billing.id])

        assert summaries[billing.id].reference_month == "2025-01"
        assert summaries[billing.id].total_amount == 100000
