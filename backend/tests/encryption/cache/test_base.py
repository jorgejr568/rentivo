from __future__ import annotations

from rentivo.encryption.cache.base import DecryptCache
from rentivo.encryption.cache.null import NullDecryptCache


def test_null_cache_satisfies_decrypt_cache_protocol():
    """``NullDecryptCache`` is the reference no-op implementation; it must
    structurally satisfy the ``DecryptCache`` Protocol."""
    assert isinstance(NullDecryptCache(), DecryptCache)


def test_objects_missing_methods_do_not_satisfy_protocol():
    class NotACache:
        pass

    assert not isinstance(NotACache(), DecryptCache)
