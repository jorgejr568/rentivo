from datetime import date

from rentivo.models.billing import Billing, BillingItem, ItemType, ReadjustmentIndex
from rentivo.services.bcb_sgs_client import IGPM_SERIES, IPCA_SERIES
from rentivo.services.readjustment_service import ReadjustmentService, readjust_amount, series_for_index


def test_series_for_index():
    assert series_for_index(ReadjustmentIndex.IGPM) == IGPM_SERIES
    assert series_for_index(ReadjustmentIndex.IPCA) == IPCA_SERIES
    assert series_for_index(ReadjustmentIndex.NONE) is None


def test_readjust_amount_rounds_half():
    # 285000 * 1.05 = 299250.0 -> 299250
    assert readjust_amount(285000, 5.0) == 299250
    # 100001 * (1 + 3.333/100) = 103334.333... -> 103334
    assert readjust_amount(100001, 3.333) == 103334


def test_preview_targets_only_fixed_items():
    billing = Billing(
        name="Apt 1",
        items=[
            BillingItem(id=1, description="Aluguel", amount=285000, item_type=ItemType.FIXED),
            BillingItem(id=2, description="Água", amount=0, item_type=ItemType.VARIABLE),
        ],
    )
    service = ReadjustmentService(billing_service=None)  # preview needs no repo
    preview = service.preview(billing, pct=10.0)
    assert preview == [
        {"id": 1, "description": "Aluguel", "old_amount": 285000, "new_amount": 313500},
    ]


def test_apply_updates_fixed_items_and_date():
    captured = {}

    class FakeBillingService:
        def update_billing(self, billing):
            captured["billing"] = billing
            return billing

    billing = Billing(
        id=7,
        name="Apt 1",
        items=[
            BillingItem(id=1, description="Aluguel", amount=285000, item_type=ItemType.FIXED),
            BillingItem(id=2, description="Água", amount=0, item_type=ItemType.VARIABLE),
        ],
        readjustment_index=ReadjustmentIndex.IGPM,
    )
    service = ReadjustmentService(billing_service=FakeBillingService())
    updated = service.apply(billing, pct=10.0, applied_on=date(2026, 6, 14))
    assert captured["billing"].items[0].amount == 313500  # FIXED readjusted
    assert captured["billing"].items[1].amount == 0  # VARIABLE untouched
    assert updated.last_readjustment_date == "2026-06-14"
