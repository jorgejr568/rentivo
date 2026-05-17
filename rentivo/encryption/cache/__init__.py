"""Short-lived ciphertext → plaintext caches for ``EncryptionBackend.decrypt``.

The cache is consulted by ``CachingEncryptionBackend``; concrete encryption
backends remain pure. Three implementations are available:

- ``NullDecryptCache`` — no-op (default, selected when caching is disabled).
- ``MemoryDecryptCache`` — process-local TTL cache.
- ``RedisDecryptCache`` — shared TTL cache, requires a Redis URL.
"""
