from unittest.mock import MagicMock

from rentivo.cache.null import NullKVCache
from rentivo.models.dashboard import (
    DashboardScope,
)
from rentivo.repositories.base import DashboardKPIs, InadimplenciaResult
from rentivo.services.dashboard_cache import DashboardCache
from rentivo.services.dashboard_service import DashboardService


def _fake_repo(*, current_kpis, prior_kpis, inad, series=None, statuses=None, top=None):
    repo = MagicMock()

    def kpis_side_effect(scope, reference_month):
        if reference_month.endswith("-05"):
            return current_kpis
        return prior_kpis

    repo.kpis.side_effect = kpis_side_effect
    repo.inadimplencia.return_value = inad
    repo.monthly_series.return_value = series or []
    repo.status_counts.return_value = statuses or []
    repo.top_billings.return_value = top or []
    return repo


def test_taxa_recebimento_computed():
    repo = _fake_repo(
        current_kpis=DashboardKPIs(faturado_cents=10000, recebido_cents=8000, em_aberto_cents=2000),
        prior_kpis=DashboardKPIs(faturado_cents=5000, recebido_cents=2000, em_aberto_cents=3000),
        inad=InadimplenciaResult(amount_cents=0, count=0),
    )
    svc = DashboardService(repo, DashboardCache(NullKVCache()), clock=lambda: __import__("datetime").date(2026, 5, 20))
    metrics = svc.get_metrics(DashboardScope(kind="user", id=1))

    assert metrics.taxa_recebimento.pct == 80.0
    assert metrics.taxa_recebimento.delta_pct == 80.0 - 40.0


def test_taxa_pct_none_when_faturado_zero():
    repo = _fake_repo(
        current_kpis=DashboardKPIs(faturado_cents=0, recebido_cents=0, em_aberto_cents=0),
        prior_kpis=DashboardKPIs(faturado_cents=0, recebido_cents=0, em_aberto_cents=0),
        inad=InadimplenciaResult(amount_cents=0, count=0),
    )
    svc = DashboardService(repo, DashboardCache(NullKVCache()), clock=lambda: __import__("datetime").date(2026, 5, 20))
    metrics = svc.get_metrics(DashboardScope(kind="user", id=1))
    assert metrics.taxa_recebimento.pct is None
    assert metrics.taxa_recebimento.delta_pct is None


def test_em_aberto_has_no_delta():
    repo = _fake_repo(
        current_kpis=DashboardKPIs(faturado_cents=10000, recebido_cents=8000, em_aberto_cents=2000),
        prior_kpis=DashboardKPIs(faturado_cents=5000, recebido_cents=2000, em_aberto_cents=3000),
        inad=InadimplenciaResult(amount_cents=0, count=0),
    )
    svc = DashboardService(repo, DashboardCache(NullKVCache()), clock=lambda: __import__("datetime").date(2026, 5, 20))
    metrics = svc.get_metrics(DashboardScope(kind="user", id=1))
    assert metrics.em_aberto.delta is None


def test_faturado_delta_pct_computed():
    repo = _fake_repo(
        current_kpis=DashboardKPIs(faturado_cents=15000, recebido_cents=0, em_aberto_cents=0),
        prior_kpis=DashboardKPIs(faturado_cents=10000, recebido_cents=0, em_aberto_cents=0),
        inad=InadimplenciaResult(amount_cents=0, count=0),
    )
    svc = DashboardService(repo, DashboardCache(NullKVCache()), clock=lambda: __import__("datetime").date(2026, 5, 20))
    metrics = svc.get_metrics(DashboardScope(kind="user", id=1))
    assert metrics.faturado.delta.amount_cents == 5000
    assert metrics.faturado.delta.pct == 50.0


def test_cache_hit_short_circuits():
    repo = _fake_repo(
        current_kpis=DashboardKPIs(faturado_cents=1, recebido_cents=0, em_aberto_cents=0),
        prior_kpis=DashboardKPIs(faturado_cents=0, recebido_cents=0, em_aberto_cents=0),
        inad=InadimplenciaResult(amount_cents=0, count=0),
    )
    from rentivo.cache.memory import MemoryKVCache

    cache = DashboardCache(MemoryKVCache(ttl_seconds=60, max_entries=10, enable_cleanup_thread=False))
    svc = DashboardService(repo, cache, clock=lambda: __import__("datetime").date(2026, 5, 20))

    svc.get_metrics(DashboardScope(kind="user", id=1))
    svc.get_metrics(DashboardScope(kind="user", id=1))

    # Repo called only on the first invocation
    assert repo.kpis.call_count == 2  # current + prior, called once
    assert repo.monthly_series.call_count == 1
