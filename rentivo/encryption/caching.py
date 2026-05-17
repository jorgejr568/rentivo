from __future__ import annotations

from rentivo.encryption.base import EncryptionBackend
from rentivo.encryption.cache.base import DecryptCache


class CachingEncryptionBackend(EncryptionBackend):
    """Decorator that fronts ``EncryptionBackend.decrypt`` / ``decrypt_many``
    with a short-lived ciphertext → plaintext cache.

    ``encrypt`` and ``is_encrypted`` are unconditionally delegated to ``inner``
    — caching writes would buy almost nothing (plaintexts rarely repeat across
    writes) and would broaden the plaintext residency window unnecessarily.
    """

    def __init__(self, inner: EncryptionBackend, cache: DecryptCache) -> None:
        self.inner = inner
        self.cache = cache

    def encrypt(self, plaintext: str) -> str:
        return self.inner.encrypt(plaintext)

    def is_encrypted(self, value: str) -> bool:
        return self.inner.is_encrypted(value)

    def decrypt(self, value: str) -> str:
        hit = self.cache.get_many([value])
        if value in hit:
            return hit[value]
        plaintext = self.inner.decrypt(value)
        self.cache.set_many({value: plaintext})
        return plaintext

    def decrypt_many(self, values: list[str]) -> list[str]:
        if not values:
            return []
        # De-duplicate misses while preserving first-seen order, so the inner
        # backend's decrypt_many is called once per unique ciphertext.
        unique_in_order: list[str] = []
        seen: set[str] = set()
        for v in values:
            if v not in seen:
                seen.add(v)
                unique_in_order.append(v)

        cached = self.cache.get_many(unique_in_order)
        misses = [v for v in unique_in_order if v not in cached]
        if misses:
            miss_plaintexts = self.inner.decrypt_many(misses)
            fresh = dict(zip(misses, miss_plaintexts))
            self.cache.set_many(fresh)
        else:
            fresh = {}

        resolved = {**cached, **fresh}
        return [resolved[v] for v in values]
