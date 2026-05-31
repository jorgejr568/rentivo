from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

try:
    import redis  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - exercised via patched import in tests
    redis = None  # type: ignore[assignment]

logger = structlog.get_logger(__name__)

_KEY_PREFIX = "rentivo:cache:v1:"


def _redis_key(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return _KEY_PREFIX + digest


class RedisCache:
    """Shared TTL cache backed by Redis. Values are stored as JSON.

    Failure-mode: any exception from the redis client (network, decode) is
    swallowed and logged at WARNING; reads degrade to "cache miss", writes are
    silently dropped, so callers still recompute and succeed — just without the
    cache speedup.

    Constructor takes an injected client so tests can supply ``fakeredis``.
    Production callers should use ``RedisCache.from_url(...)``.
    """

    def __init__(self, client: Any, ttl_seconds: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    @classmethod
    def from_url(cls, url: str, ttl_seconds: int) -> "RedisCache":
        if redis is None:  # pragma: no cover - exercised only when the extra is absent
            raise ImportError("redis is required for RedisCache. Install it with: pip install 'rentivo[cache]'")
        client = redis.from_url(url, decode_responses=True)
        return cls(client=client, ttl_seconds=ttl_seconds)

    def get(self, key: str) -> Any | None:
        try:
            raw = self._client.get(_redis_key(key))
        except Exception as exc:
            logger.warning("cache_redis_get_failed", error=str(exc))
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception as exc:
            logger.warning("cache_redis_decode_failed", error=str(exc))
            return None

    def set(self, key: str, value: Any) -> None:
        try:
            payload = json.dumps(value)
        except (TypeError, ValueError) as exc:
            logger.warning("cache_redis_encode_failed", error=str(exc))
            return
        try:
            self._client.set(_redis_key(key), payload, ex=self._ttl_seconds)
        except Exception as exc:
            logger.warning("cache_redis_set_failed", error=str(exc))

    def clear(self) -> None:
        try:
            keys = list(self._client.scan_iter(match=_KEY_PREFIX + "*"))
            if keys:
                self._client.delete(*keys)
        except Exception as exc:
            logger.warning("cache_redis_clear_failed", error=str(exc))

    def close(self) -> None:
        try:
            self._client.close()
        except Exception as exc:  # pragma: no cover - close paths rarely fail
            logger.warning("cache_redis_close_failed", error=str(exc))
