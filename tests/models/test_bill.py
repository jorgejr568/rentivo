from datetime import datetime

from freezegun import freeze_time

from rentivo.models.bill import SP_TZ, Bill, BillLineItem
from rentivo.models.billing import ItemType


class TestBillLineItem:
    def test_construction(self):
        item = BillLineItem(description="Water", amount=5000, item_type=ItemType.VARIABLE)
        assert item.id is None
        assert item.bill_id is None
        assert item.sort_order == 0


class TestBill:
    def test_defaults(self):
        bill = Bill(billing_id=1, reference_month="2025-03")
        assert bill.id is None
        assert bill.uuid == ""
        assert bill.total_amount == 0
        assert bill.line_items == []
        assert bill.pdf_path is None
        assert bill.notes == ""
        assert bill.due_date is None
        assert bill.paid_at is None


class TestIsOverdue:
    @freeze_time("2025-04-15 12:00:00", tz_offset=-3)
    def test_overdue_when_past_due(self):
        bill = Bill(
            billing_id=1,
            reference_month="2025-03",
            due_date="10/04/2025",
        )
        assert bill.is_overdue is True

    @freeze_time("2025-04-05 12:00:00", tz_offset=-3)
    def test_not_overdue_before_due(self):
        bill = Bill(
            billing_id=1,
            reference_month="2025-03",
            due_date="10/04/2025",
        )
        assert bill.is_overdue is False

    def test_not_overdue_when_paid(self):
        bill = Bill(
            billing_id=1,
            reference_month="2025-03",
            due_date="01/01/2020",
            paid_at=datetime(2025, 1, 15, tzinfo=SP_TZ),
        )
        assert bill.is_overdue is False

    def test_not_overdue_no_due_date(self):
        bill = Bill(billing_id=1, reference_month="2025-03")
        assert bill.is_overdue is False

    def test_not_overdue_invalid_date(self):
        bill = Bill(billing_id=1, reference_month="2025-03", due_date="invalid")
        assert bill.is_overdue is False


class TestPaymentStatus:
    def test_paid(self):
        bill = Bill(
            billing_id=1,
            reference_month="2025-03",
            paid_at=datetime(2025, 3, 15, tzinfo=SP_TZ),
        )
        assert bill.payment_status == "paid"

    @freeze_time("2025-04-15 12:00:00", tz_offset=-3)
    def test_overdue(self):
        bill = Bill(
            billing_id=1,
            reference_month="2025-03",
            due_date="10/04/2025",
        )
        assert bill.payment_status == "overdue"

    @freeze_time("2025-04-05 12:00:00", tz_offset=-3)
    def test_pending(self):
        bill = Bill(
            billing_id=1,
            reference_month="2025-03",
            due_date="10/04/2025",
        )
        assert bill.payment_status == "pending"
