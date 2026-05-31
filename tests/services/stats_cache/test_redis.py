from __future__ import annotations

from unittest.mock import patch

import fakeredis

from rentivo.services.stats_cache.redis import RedisStatsCache, _redis_key


def _client():
    return fakeredis.FakeStrictRedis(decode_responses=True)


def test_set_then_get_round_trips_through_json(sample_stats):
    cache = RedisStatsCache(client=_client(), ttl_seconds=60)
    assert cache.get("missing") is None
    cache.set("k", sample_stats)
    restored = cache.get("k")
    assert restored == sample_stats
    assert restored.current[1].status == "sent"


def test_set_applies_ttl(sample_stats):
    client = _client()
    cache = RedisStatsCache(client=client, ttl_seconds=42)
    cache.set("k", sample_stats)
    assert client.ttl(_redis_key("k")) == 42


def test_clear_removes_only_namespaced_keys(sample_stats):
    client = _client()
    client.set("unrelated", "keep-me")
    cache = RedisStatsCache(client=client, ttl_seconds=60)
    cache.set("a", sample_stats)
    cache.set("b", sample_stats)

    cache.clear()

    assert cache.get("a") is None
    assert client.get("unrelated") == "keep-me"


def test_get_is_fail_open_on_client_error(sample_stats):
    class Boom:
        def get(self, *_a, **_k):
            raise RuntimeError("redis down")

    cache = RedisStatsCache(client=Boom(), ttl_seconds=60)
    assert cache.get("k") is None  # degrades to a miss, does not raise


def test_get_is_fail_open_on_bad_payload():
    client = _client()
    client.set(_redis_key("k"), "{not-json")
    cache = RedisStatsCache(client=client, ttl_seconds=60)
    assert cache.get("k") is None


def test_set_is_fail_open_on_client_error(sample_stats):
    class Boom:
        def set(self, *_a, **_k):
            raise RuntimeError("redis down")

    cache = RedisStatsCache(client=Boom(), ttl_seconds=60)
    cache.set("k", sample_stats)  # must not raise


def test_clear_is_fail_open_on_client_error():
    class Boom:
        def scan_iter(self, *_a, **_k):
            raise RuntimeError("redis down")

    cache = RedisStatsCache(client=Boom(), ttl_seconds=60)
    cache.clear()  # must not raise


def test_close_closes_the_client():
    closed = {"v": False}

    class Client:
        def close(self):
            closed["v"] = True

    RedisStatsCache(client=Client(), ttl_seconds=60).close()
    assert closed["v"] is True


def test_from_url_builds_client(sample_stats):
    fake = _client()
    with patch("redis.from_url", return_value=fake) as from_url:
        cache = RedisStatsCache.from_url("redis://localhost:6379/0", ttl_seconds=30)
    from_url.assert_called_once()
    cache.set("k", sample_stats)
    assert cache.get("k") == sample_stats
