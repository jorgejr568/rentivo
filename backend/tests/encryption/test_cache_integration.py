from __future__ import annotations

from unittest.mock import patch

from rentivo.encryption.base64 import Base64Backend
from rentivo.encryption.cache.memory import MemoryDecryptCache
from rentivo.encryption.caching import CachingEncryptionBackend


def test_repeated_decrypt_many_uses_cache_on_second_call():
    """First call populates the cache; second call must not re-invoke inner."""
    inner = Base64Backend()
    cache = MemoryDecryptCache(
        ttl_seconds=60,
        max_entries=100,
        enable_cleanup_thread=False,
    )
    backend = CachingEncryptionBackend(inner=inner, cache=cache)

    plaintexts = ["alice@example.com", "bob@example.com", "carol@example.com"]
    ciphertexts = [inner.encrypt(p) for p in plaintexts]

    # First call: cache is cold — every value goes through inner.
    with patch.object(inner, "decrypt_many", wraps=inner.decrypt_many) as spy:
        first = backend.decrypt_many(ciphertexts)
        assert first == plaintexts
        spy.assert_called_once_with(ciphertexts)

    # Second call: every value is cached — inner is never invoked.
    with patch.object(inner, "decrypt_many", wraps=inner.decrypt_many) as spy:
        second = backend.decrypt_many(ciphertexts)
        assert second == plaintexts
        spy.assert_not_called()


def test_partial_overlap_only_decrypts_misses():
    inner = Base64Backend()
    cache = MemoryDecryptCache(
        ttl_seconds=60,
        max_entries=100,
        enable_cleanup_thread=False,
    )
    backend = CachingEncryptionBackend(inner=inner, cache=cache)

    a = inner.encrypt("a")
    b = inner.encrypt("b")
    c = inner.encrypt("c")

    backend.decrypt_many([a, b])  # cache: a, b

    with patch.object(inner, "decrypt_many", wraps=inner.decrypt_many) as spy:
        result = backend.decrypt_many([a, b, c, a])
        assert result == ["a", "b", "c", "a"]
        # Inner is invoked once, with only the unique miss.
        spy.assert_called_once_with([c])
