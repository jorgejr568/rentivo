from __future__ import annotations

from rentivo.cache.null import NullCache


def test_null_cache_never_stores(value):
    cache = NullCache()
    cache.set("k", value)
    assert cache.get("k") is None
    cache.clear()
    cache.close()
