from rentivo.models.billing import Billing, ReadjustmentIndex


def test_readjustment_defaults():
    b = Billing(name="Apt 1")
    assert b.readjustment_index == ReadjustmentIndex.NONE
    assert b.readjustment_month is None
    assert b.last_readjustment_date is None


def test_readjustment_index_values():
    assert ReadjustmentIndex.IGPM.value == "igpm"
    assert ReadjustmentIndex.IPCA.value == "ipca"
    assert ReadjustmentIndex.NONE.value == "none"


def test_readjustment_fields_round_trip():
    b = Billing(
        name="Apt 1",
        readjustment_index=ReadjustmentIndex.IGPM,
        readjustment_month=6,
        last_readjustment_date="2026-06-01",
    )
    assert b.readjustment_index == ReadjustmentIndex.IGPM
    assert b.readjustment_month == 6
    assert b.last_readjustment_date == "2026-06-01"
