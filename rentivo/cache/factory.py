from __future__ import annotations

import structlog

from rentivo.cache.base import Cache
from rentivo.cache.null import NullCache
from rentivo.settings import settings

logger = structlog.get_logger(__name__)

_cache: Cache | None = None


def _build_cache() -> Cache:
    backend = settings.cache_backend
    if backend == "none":
        logger.info("cache_selected", backend="none")
        return NullCache()
    if backend == "memory":
        from rentivo.cache.memory import MemoryCache

        logger.info(
            "cache_selected",
            backend="memory",
            ttl_seconds=settings.cache_ttl_seconds,
            max_entries=settings.cache_max_entries,
        )
        return MemoryCache(
            ttl_seconds=settings.cache_ttl_seconds,
            max_entries=settings.cache_max_entries,
        )
    if backend == "redis":
        from rentivo.cache.redis import RedisCache

        logger.info("cache_selected", backend="redis", ttl_seconds=settings.cache_ttl_seconds)
        return RedisCache.from_url(
            url=settings.redis_url,
            ttl_seconds=settings.cache_ttl_seconds,
        )
    raise ValueError(f"Unsupported cache backend: {backend}")


def get_cache() -> Cache:
    """Return the process-global ``Cache``, building it on first call.

    The instance is memoised at module level so every request shares one cache
    (and, for the memory backend, one cleanup thread).
    """
    global _cache
    if _cache is None:
        _cache = _build_cache()
    return _cache


def _reset_for_tests() -> None:
    """Close and drop the cached instance so a test that monkeypatches settings
    gets a fresh backend on the next ``get_cache()`` call."""
    global _cache
    if _cache is not None:
        _cache.close()
    _cache = None
