from rentivo.cache.memory import MemoryKVCache
from rentivo.cache.null import NullKVCache
from rentivo.models.dashboard import (
    CollectionRateCard,
    DashboardMetrics,
    DashboardScope,
    InadimplenciaCard,
    KPICard,
)
from rentivo.services.dashboard_cache import DashboardCache


def _metrics(month: str = "2026-05") -> DashboardMetrics:
    return DashboardMetrics(
        reference_month=month,
        faturado=KPICard(amount_cents=100),
        recebido=KPICard(amount_cents=50),
        em_aberto=KPICard(amount_cents=50),
        inadimplencia=InadimplenciaCard(amount_cents=0, count=0),
        taxa_recebimento=CollectionRateCard(pct=50.0),
    )


def test_set_and_get_roundtrip():
    cache = DashboardCache(MemoryKVCache(ttl_seconds=60, max_entries=10, enable_cleanup_thread=False))
    scope = DashboardScope(kind="user", id=1)
    metrics = _metrics()

    cache.set(scope, metrics)
    got = cache.get(scope, "2026-05")

    assert got == metrics


def test_get_miss_returns_none():
    cache = DashboardCache(MemoryKVCache(ttl_seconds=60, max_entries=10, enable_cleanup_thread=False))
    assert cache.get(DashboardScope(kind="user", id=1), "2026-05") is None


def test_null_cache_always_misses():
    cache = DashboardCache(NullKVCache())
    cache.set(DashboardScope(kind="user", id=1), _metrics())
    assert cache.get(DashboardScope(kind="user", id=1), "2026-05") is None


def test_scope_kind_isolation():
    cache = DashboardCache(MemoryKVCache(ttl_seconds=60, max_entries=10, enable_cleanup_thread=False))
    cache.set(DashboardScope(kind="user", id=1), _metrics())
    assert cache.get(DashboardScope(kind="org", id=1), "2026-05") is None


def test_corrupt_value_returns_none(caplog):
    backend = MemoryKVCache(ttl_seconds=60, max_entries=10, enable_cleanup_thread=False)
    backend.set_many({DashboardScope(kind="user", id=1).cache_key("2026-05"): "{not valid json"})
    cache = DashboardCache(backend)
    assert cache.get(DashboardScope(kind="user", id=1), "2026-05") is None
