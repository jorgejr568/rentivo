import pytest
from pydantic import ValidationError

from rentivo.models.dashboard import (
    CollectionRateCard,
    DashboardMetrics,
    DashboardScope,
    InadimplenciaCard,
    KPICard,
    MonthlyPoint,
    StatusCount,
    TopBillingRow,
)


def test_user_scope_cache_key():
    s = DashboardScope(kind="user", id=42)
    assert s.cache_key("2026-05") == "rentivo:dash:v1:user:42:2026-05"


def test_org_scope_cache_key():
    s = DashboardScope(kind="org", id=7)
    assert s.cache_key("2026-05") == "rentivo:dash:v1:org:7:2026-05"


def test_scope_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        DashboardScope(kind="team", id=1)


def test_metrics_roundtrip_json():
    m = DashboardMetrics(
        reference_month="2026-05",
        faturado=KPICard(amount_cents=12345),
        recebido=KPICard(amount_cents=6789),
        em_aberto=KPICard(amount_cents=5556),
        inadimplencia=InadimplenciaCard(amount_cents=1000, count=2),
        taxa_recebimento=CollectionRateCard(pct=55.0, delta_pct=None),
        monthly_series=[MonthlyPoint(reference_month="2026-04", faturado_cents=1, recebido_cents=0)],
        status_counts=[StatusCount(status="paid", count=3)],
        top_billings=[TopBillingRow(uuid="u", name="Casa A", faturado_cents=10, recebido_cents=5, rate_pct=50.0)],
    )
    out = m.model_dump_json()
    back = DashboardMetrics.model_validate_json(out)
    assert back == m


def test_collection_rate_pct_may_be_none():
    c = CollectionRateCard(pct=None, delta_pct=None)
    assert c.pct is None
