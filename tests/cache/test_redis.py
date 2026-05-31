from __future__ import annotations

from unittest.mock import patch

import fakeredis

from rentivo.cache.redis import RedisCache, _redis_key


def _client():
    return fakeredis.FakeStrictRedis(decode_responses=True)


def test_set_then_get_round_trips_through_json(value):
    cache = RedisCache(client=_client(), ttl_seconds=60)
    assert cache.get("missing") is None
    cache.set("k", value)
    assert cache.get("k") == value  # equal value, fresh object after JSON round-trip


def test_set_applies_ttl(value):
    client = _client()
    cache = RedisCache(client=client, ttl_seconds=42)
    cache.set("k", value)
    assert client.ttl(_redis_key("k")) == 42


def test_clear_removes_only_namespaced_keys(value):
    client = _client()
    client.set("unrelated", "keep-me")
    cache = RedisCache(client=client, ttl_seconds=60)
    cache.set("a", value)
    cache.set("b", value)

    cache.clear()

    assert cache.get("a") is None
    assert client.get("unrelated") == "keep-me"


def test_get_is_fail_open_on_client_error():
    class Boom:
        def get(self, *_a, **_k):
            raise RuntimeError("redis down")

    cache = RedisCache(client=Boom(), ttl_seconds=60)
    assert cache.get("k") is None  # degrades to a miss, does not raise


def test_get_is_fail_open_on_bad_payload():
    client = _client()
    client.set(_redis_key("k"), "{not-json")
    cache = RedisCache(client=client, ttl_seconds=60)
    assert cache.get("k") is None


def test_set_is_fail_open_on_unserialisable_value():
    cache = RedisCache(client=_client(), ttl_seconds=60)
    cache.set("k", {"bad": object()})  # not JSON-serialisable → dropped, no raise
    assert cache.get("k") is None


def test_set_is_fail_open_on_client_error(value):
    class Boom:
        def set(self, *_a, **_k):
            raise RuntimeError("redis down")

    cache = RedisCache(client=Boom(), ttl_seconds=60)
    cache.set("k", value)  # must not raise


def test_clear_is_fail_open_on_client_error():
    class Boom:
        def scan_iter(self, *_a, **_k):
            raise RuntimeError("redis down")

    cache = RedisCache(client=Boom(), ttl_seconds=60)
    cache.clear()  # must not raise


def test_close_closes_the_client():
    closed = {"v": False}

    class Client:
        def close(self):
            closed["v"] = True

    RedisCache(client=Client(), ttl_seconds=60).close()
    assert closed["v"] is True


def test_from_url_builds_client(value):
    fake = _client()
    with patch("redis.from_url", return_value=fake) as from_url:
        cache = RedisCache.from_url("redis://localhost:6379/0", ttl_seconds=30)
    from_url.assert_called_once()
    cache.set("k", value)
    assert cache.get("k") == value
