from rentivo.services.billing_stats import BillingStats


def test_to_dict_from_dict_roundtrips_expenses():
    stats = BillingStats(year=2026, expected=1000, received=600, total_expenses=150, net_income=450)
    data = stats.to_dict()
    assert data["total_expenses"] == 150
    assert data["net_income"] == 450
    restored = BillingStats.from_dict(data)
    assert restored.total_expenses == 150
    assert restored.net_income == 450
    assert restored == stats


def test_defaults():
    stats = BillingStats()
    assert stats.total_expenses == 0
    assert stats.net_income == 0
