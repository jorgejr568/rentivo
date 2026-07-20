"""Tests for SQLAlchemyBillRepository.list_summaries — the lightweight
all-bills-per-billing query that backs the dashboard / organization KPIs."""

from __future__ import annotations


class TestListSummaries:
    def _billing(self, billing_repo, sample_billing, **overrides):
        return billing_repo.create(sample_billing(**overrides))

    def test_empty_input_returns_empty(self, bill_repo):
        assert bill_repo.list_summaries([]) == []

    def test_billing_with_no_bills_yields_nothing(self, bill_repo, billing_repo, sample_billing):
        billing = self._billing(billing_repo, sample_billing)
        assert bill_repo.list_summaries([billing.id]) == []

    def test_returns_all_bills_newest_first_per_billing(self, bill_repo, billing_repo, sample_billing, sample_bill):
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

        summaries = bill_repo.list_summaries([billing.id])

        assert [s.reference_month for s in summaries] == ["2025-03", "2025-02", "2025-01"]
        assert summaries[0].total_amount == 300000
        assert summaries[0].status == "sent"

    def test_maps_multiple_billings(self, bill_repo, billing_repo, sample_billing, sample_bill):
        a = self._billing(billing_repo, sample_billing, name="A")
        b = self._billing(billing_repo, sample_billing, name="B")
        c = self._billing(billing_repo, sample_billing, name="C")  # no bills
        bill_repo.create(
            sample_bill(billing_id=a.id, reference_month="2026-05", total_amount=351200, status="delayed_payment")
        )
        bill_repo.create(sample_bill(billing_id=b.id, reference_month="2026-05", total_amount=171500, status="paid"))

        summaries = bill_repo.list_summaries([a.id, b.id, c.id])

        by_billing = {s.billing_id for s in summaries}
        assert by_billing == {a.id, b.id}
        a_summary = next(s for s in summaries if s.billing_id == a.id)
        assert a_summary.status == "delayed_payment"
        assert a_summary.due_date is not None

    def test_ignores_soft_deleted_bills(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._billing(billing_repo, sample_billing)
        bill_repo.create(
            sample_bill(billing_id=billing.id, reference_month="2025-01", total_amount=100000, status="paid")
        )
        newer = bill_repo.create(
            sample_bill(billing_id=billing.id, reference_month="2025-06", total_amount=600000, status="sent")
        )

        bill_repo.delete(newer.id)
        summaries = bill_repo.list_summaries([billing.id])

        assert [s.reference_month for s in summaries] == ["2025-01"]
        assert summaries[0].total_amount == 100000
