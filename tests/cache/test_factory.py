from __future__ import annotations

from unittest.mock import patch

import fakeredis
import pytest

from rentivo.cache.memory import MemoryCache
from rentivo.cache.null import NullCache
from rentivo.cache.redis import RedisCache


@patch("rentivo.cache.factory.settings")
def test_none_backend_returns_null_cache(mock_settings):
    mock_settings.cache_backend = "none"
    from rentivo.cache.factory import get_cache

    assert isinstance(get_cache(), NullCache)


@patch("rentivo.cache.factory.settings")
def test_memory_backend(mock_settings):
    mock_settings.cache_backend = "memory"
    mock_settings.cache_ttl_seconds = 60
    mock_settings.cache_max_entries = 128
    from rentivo.cache.factory import get_cache

    assert isinstance(get_cache(), MemoryCache)


@patch("rentivo.cache.factory.settings")
def test_redis_backend(mock_settings):
    mock_settings.cache_backend = "redis"
    mock_settings.cache_ttl_seconds = 60
    mock_settings.redis_url = "redis://localhost:6379/0"
    with patch("redis.from_url", return_value=fakeredis.FakeStrictRedis(decode_responses=True)):
        from rentivo.cache.factory import get_cache

        assert isinstance(get_cache(), RedisCache)


@patch("rentivo.cache.factory.settings")
def test_unsupported_backend_raises(mock_settings):
    mock_settings.cache_backend = "memcached"
    from rentivo.cache.factory import get_cache

    with pytest.raises(ValueError, match="Unsupported cache backend"):
        get_cache()


@patch("rentivo.cache.factory.settings")
def test_get_is_memoised_until_reset(mock_settings):
    mock_settings.cache_backend = "memory"
    mock_settings.cache_ttl_seconds = 60
    mock_settings.cache_max_entries = 128
    from rentivo.cache import factory

    first = factory.get_cache()
    assert factory.get_cache() is first
    factory._reset_for_tests()
    assert factory.get_cache() is not first
