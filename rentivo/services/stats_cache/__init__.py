"""Pluggable cache for billing KPI rollups (``BillingStats``).

Mirrors the encryption decrypt-cache: three interchangeable backends selected by
``RENTIVO_STATS_CACHE_BACKEND`` (its own env, independent of the encryption
cache):

- ``NullStatsCache`` — no-op.
- ``MemoryStatsCache`` — process-local TTL cache.
- ``RedisStatsCache`` — shared TTL cache, requires ``RENTIVO_REDIS_URL``.

The cache is a performance layer, never a correctness one: every backend is
fail-open (a backend error degrades to a cache miss / dropped write).
"""
