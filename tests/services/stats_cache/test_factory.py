from __future__ import annotations

from unittest.mock import patch

import fakeredis
import pytest

from rentivo.services.stats_cache.memory import MemoryStatsCache
from rentivo.services.stats_cache.null import NullStatsCache
from rentivo.services.stats_cache.redis import RedisStatsCache


@patch("rentivo.services.stats_cache.factory.settings")
def test_none_backend_returns_null_cache(mock_settings):
    mock_settings.stats_cache_backend = "none"
    from rentivo.services.stats_cache.factory import get_stats_cache

    assert isinstance(get_stats_cache(), NullStatsCache)


@patch("rentivo.services.stats_cache.factory.settings")
def test_memory_backend(mock_settings):
    mock_settings.stats_cache_backend = "memory"
    mock_settings.stats_cache_ttl_seconds = 60
    mock_settings.stats_cache_max_entries = 128
    from rentivo.services.stats_cache.factory import get_stats_cache

    assert isinstance(get_stats_cache(), MemoryStatsCache)


@patch("rentivo.services.stats_cache.factory.settings")
def test_redis_backend(mock_settings):
    mock_settings.stats_cache_backend = "redis"
    mock_settings.stats_cache_ttl_seconds = 60
    mock_settings.redis_url = "redis://localhost:6379/0"
    with patch("redis.from_url", return_value=fakeredis.FakeStrictRedis(decode_responses=True)):
        from rentivo.services.stats_cache.factory import get_stats_cache

        assert isinstance(get_stats_cache(), RedisStatsCache)


@patch("rentivo.services.stats_cache.factory.settings")
def test_unsupported_backend_raises(mock_settings):
    mock_settings.stats_cache_backend = "memcached"
    from rentivo.services.stats_cache.factory import get_stats_cache

    with pytest.raises(ValueError, match="Unsupported stats cache backend"):
        get_stats_cache()


@patch("rentivo.services.stats_cache.factory.settings")
def test_get_is_memoised_until_reset(mock_settings):
    mock_settings.stats_cache_backend = "memory"
    mock_settings.stats_cache_ttl_seconds = 60
    mock_settings.stats_cache_max_entries = 128
    from rentivo.services.stats_cache import factory

    first = factory.get_stats_cache()
    assert factory.get_stats_cache() is first
    factory._reset_for_tests()
    assert factory.get_stats_cache() is not first
