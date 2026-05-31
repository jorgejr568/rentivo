from __future__ import annotations

import structlog

from rentivo.services.stats_cache.base import StatsCache
from rentivo.services.stats_cache.null import NullStatsCache
from rentivo.settings import settings

logger = structlog.get_logger(__name__)

_cache: StatsCache | None = None


def _build_cache() -> StatsCache:
    backend = settings.stats_cache_backend
    if backend == "none":
        logger.info("stats_cache_selected", backend="none")
        return NullStatsCache()
    if backend == "memory":
        from rentivo.services.stats_cache.memory import MemoryStatsCache

        logger.info(
            "stats_cache_selected",
            backend="memory",
            ttl_seconds=settings.stats_cache_ttl_seconds,
            max_entries=settings.stats_cache_max_entries,
        )
        return MemoryStatsCache(
            ttl_seconds=settings.stats_cache_ttl_seconds,
            max_entries=settings.stats_cache_max_entries,
        )
    if backend == "redis":
        from rentivo.services.stats_cache.redis import RedisStatsCache

        logger.info("stats_cache_selected", backend="redis", ttl_seconds=settings.stats_cache_ttl_seconds)
        return RedisStatsCache.from_url(
            url=settings.redis_url,
            ttl_seconds=settings.stats_cache_ttl_seconds,
        )
    raise ValueError(f"Unsupported stats cache backend: {backend}")


def get_stats_cache() -> StatsCache:
    """Return the process-global ``StatsCache``, building it on first call.

    The instance is memoised at module level so every request shares one cache
    (and, for the memory backend, one cleanup thread).
    """
    global _cache
    if _cache is None:
        _cache = _build_cache()
    return _cache


def _reset_for_tests() -> None:
    """Close and drop the cached instance so a test that monkeypatches settings
    gets a fresh backend on the next ``get_stats_cache()`` call."""
    global _cache
    if _cache is not None:
        _cache.close()
    _cache = None
