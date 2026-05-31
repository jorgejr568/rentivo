from __future__ import annotations

from rentivo.services.stats_cache.null import NullStatsCache


def test_null_cache_never_stores(sample_stats):
    cache = NullStatsCache()
    cache.set("k", sample_stats)
    assert cache.get("k") is None
    cache.clear()
    cache.close()
