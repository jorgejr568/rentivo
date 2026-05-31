"""Generic, pluggable key→value cache.

Three interchangeable backends selected by ``RENTIVO_CACHE_BACKEND`` (its own
env, independent of the encryption decrypt-cache):

- ``NullCache`` — no-op.
- ``MemoryCache`` — process-local TTL cache.
- ``RedisCache`` — shared TTL cache, requires ``RENTIVO_REDIS_URL``.

Values must be JSON-serialisable so any backend (notably Redis) can store them.
The cache is a performance layer, never a correctness one: every backend is
fail-open (a backend error degrades to a cache miss / dropped write).
"""

from rentivo.cache.base import Cache
from rentivo.cache.factory import get_cache

__all__ = ["Cache", "get_cache"]
