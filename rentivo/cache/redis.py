from __future__ import annotations

import hashlib
from typing import Any

import structlog

try:
    import redis  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - exercised via patched import in tests
    redis = None  # type: ignore[assignment]

logger = structlog.get_logger(__name__)


class RedisKVCache:
    """Shared TTL cache backed by Redis.

    Failure-mode: any exception from the redis client (network, decode) is
    swallowed and logged at WARNING. Reads degrade to "cache miss"; writes
    are silently dropped. The decoration layer falls back to the inner
    encryption backend, so requests still succeed — just without the cache
    speedup.

    Constructor takes an injected client so tests can supply ``fakeredis``.
    Production callers should use ``RedisKVCache.from_url(...)``.
    """

    def __init__(self, client: Any, ttl_seconds: int, key_prefix: str = "") -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._key_prefix = key_prefix

    def _hashed_key(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._key_prefix + digest

    @classmethod
    def from_url(cls, url: str, ttl_seconds: int, key_prefix: str = "") -> "RedisKVCache":
        if redis is None:
            raise ImportError("redis is required for RedisKVCache. Install it with: pip install 'rentivo[cache]'")
        client = redis.from_url(url, decode_responses=True)
        return cls(client=client, ttl_seconds=ttl_seconds, key_prefix=key_prefix)

    def get_many(self, keys: list[str]) -> dict[str, str]:
        if not keys:
            return {}
        hashed = [self._hashed_key(k) for k in keys]
        try:
            values = self._client.mget(hashed)
        except Exception as exc:
            logger.warning("decrypt_cache_redis_get_failed", error=str(exc))
            return {}
        out: dict[str, str] = {}
        for original, value in zip(keys, values):
            if value is None:
                continue
            out[original] = value
        return out

    def set_many(self, items: dict[str, str]) -> None:
        if not items:
            return
        try:
            with self._client.pipeline() as pipe:
                for k, v in items.items():
                    pipe.set(self._hashed_key(k), v, ex=self._ttl_seconds)
                pipe.execute()
        except Exception as exc:
            logger.warning("decrypt_cache_redis_set_failed", error=str(exc))

    def close(self) -> None:
        try:
            self._client.close()
        except Exception as exc:  # pragma: no cover - close paths rarely fail
            logger.warning("decrypt_cache_redis_close_failed", error=str(exc))
