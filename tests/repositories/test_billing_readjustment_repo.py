from rentivo.models.billing import Billing, BillingItem, ItemType, ReadjustmentIndex
from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository


def test_create_and_read_roundtrips_readjustment(billing_repo: SQLAlchemyBillingRepository):
    created = billing_repo.create(
        Billing(
            name="Apt 9",
            items=[BillingItem(description="Aluguel", amount=285000, item_type=ItemType.FIXED)],
            readjustment_index=ReadjustmentIndex.IPCA,
            readjustment_month=3,
            last_readjustment_date="2026-03-01",
        )
    )
    loaded = billing_repo.get_by_id(created.id)
    assert loaded.readjustment_index == ReadjustmentIndex.IPCA
    assert loaded.readjustment_month == 3
    assert loaded.last_readjustment_date == "2026-03-01"


def test_defaults_when_unset(billing_repo: SQLAlchemyBillingRepository):
    created = billing_repo.create(
        Billing(name="Apt 1", items=[BillingItem(description="Aluguel", amount=100000, item_type=ItemType.FIXED)])
    )
    loaded = billing_repo.get_by_id(created.id)
    assert loaded.readjustment_index == ReadjustmentIndex.NONE
    assert loaded.readjustment_month is None
    assert loaded.last_readjustment_date is None


def test_update_persists_readjustment(billing_repo: SQLAlchemyBillingRepository):
    created = billing_repo.create(
        Billing(name="Apt 2", items=[BillingItem(description="Aluguel", amount=100000, item_type=ItemType.FIXED)])
    )
    created.readjustment_index = ReadjustmentIndex.IGPM
    created.readjustment_month = 6
    created.last_readjustment_date = "2026-06-14"
    billing_repo.update(created)
    loaded = billing_repo.get_by_id(created.id)
    assert loaded.readjustment_index == ReadjustmentIndex.IGPM
    assert loaded.readjustment_month == 6
    assert loaded.last_readjustment_date == "2026-06-14"
