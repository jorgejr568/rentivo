from rentivo.models.billing import Billing, BillingItem, ItemType


class TestItemType:
    def test_values(self):
        assert ItemType.FIXED.value == "fixed"
        assert ItemType.VARIABLE.value == "variable"
        assert ItemType.EXTRA.value == "extra"

    def test_from_string(self):
        assert ItemType("fixed") is ItemType.FIXED


class TestBillingItem:
    def test_defaults(self):
        item = BillingItem(description="Rent", item_type=ItemType.FIXED)
        assert item.id is None
        assert item.billing_id is None
        assert item.amount == 0
        assert item.sort_order == 0


class TestBilling:
    def test_defaults(self):
        billing = Billing(name="Apt 101")
        assert billing.id is None
        assert billing.uuid == ""
        assert billing.description == ""
        assert billing.pix_key == ""
        assert billing.items == []
        assert billing.created_at is None
        assert billing.deleted_at is None

    def test_with_items(self):
        items = [
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ]
        billing = Billing(name="Apt 201", items=items)
        assert len(billing.items) == 1
        assert billing.items[0].amount == 100000
