from __future__ import annotations

from rentivo.cache.base import KVCache
from rentivo.cache.null import NullKVCache


def test_null_cache_satisfies_kv_cache_protocol():
    """``NullKVCache`` is the reference no-op implementation; it must
    structurally satisfy the ``KVCache`` Protocol."""
    assert isinstance(NullKVCache(), KVCache)


def test_objects_missing_methods_do_not_satisfy_protocol():
    class NotACache:
        pass

    assert not isinstance(NotACache(), KVCache)
