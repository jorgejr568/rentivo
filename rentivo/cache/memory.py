from __future__ import annotations

import threading
import time
from typing import Callable

import structlog
from cachetools import TTLCache

logger = structlog.get_logger(__name__)


class MemoryKVCache:
    """Process-local TTL cache for decrypted plaintexts.

    Wraps ``cachetools.TTLCache`` with an ``RLock`` because ``cachetools`` is
    not thread-safe and KMS ``decrypt_many`` fans out via a thread pool.

    A daemon cleanup thread actively sweeps expired entries so memory does
    not grow unbounded between reads.
    """

    def __init__(
        self,
        ttl_seconds: int,
        max_entries: int,
        *,
        timer: Callable[[], float] | None = None,
        enable_cleanup_thread: bool = True,
        cleanup_interval_seconds: float | None = None,
    ) -> None:
        self._timer = timer or time.time
        self._lock = threading.RLock()
        self._cache: TTLCache[str, str] = TTLCache(
            maxsize=max_entries,
            ttl=ttl_seconds,
            timer=self._timer,
        )
        self._stop_event: threading.Event | None = None
        self._cleanup_thread: threading.Thread | None = None

        if enable_cleanup_thread:
            interval = self._effective_cleanup_interval(ttl_seconds, cleanup_interval_seconds)
            self._stop_event = threading.Event()
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop,
                args=(interval,),
                name="MemoryKVCache-cleanup",
                daemon=True,
            )
            self._cleanup_thread.start()

    @staticmethod
    def _effective_cleanup_interval(ttl_seconds: int, override: float | None) -> float:
        if override is not None:
            return float(override)
        return max(1.0, ttl_seconds / 4.0)

    def _cleanup_loop(self, interval: float) -> None:
        stop = self._stop_event
        assert stop is not None
        while not stop.wait(interval):
            with self._lock:
                # cachetools TTLCache exposes ``expire()`` to drop everything
                # whose TTL has elapsed under the configured timer.
                self._cache.expire()

    def get_many(self, keys: list[str]) -> dict[str, str]:
        if not keys:
            return {}
        out: dict[str, str] = {}
        with self._lock:
            for k in keys:
                try:
                    out[k] = self._cache[k]
                except KeyError:
                    continue
        return out

    def set_many(self, items: dict[str, str]) -> None:
        if not items:
            return
        with self._lock:
            for k, v in items.items():
                self._cache[k] = v

    def close(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._cleanup_thread is not None:
            self._cleanup_thread.join(timeout=2.0)
        self._stop_event = None
        self._cleanup_thread = None
