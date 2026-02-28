from rentivo.models.bill import Bill, BillLineItem, BillStatus
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
        assert bill.status == BillStatus.DRAFT.value
        assert bill.status_updated_at is None


class TestBillStatus:
    def test_default_status_is_draft(self):
        bill = Bill(billing_id=1, reference_month="2025-03")
        assert bill.status == "draft"

    def test_status_can_be_set(self):
        bill = Bill(billing_id=1, reference_month="2025-03", status="paid")
        assert bill.status == "paid"

    def test_all_status_values(self):
        for s in BillStatus:
            bill = Bill(billing_id=1, reference_month="2025-03", status=s.value)
            assert bill.status == s.value
