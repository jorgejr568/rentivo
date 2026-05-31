from __future__ import annotations

import threading
import time
from typing import Callable

import structlog
from cachetools import TTLCache

from rentivo.services.billing_stats import BillingStats

logger = structlog.get_logger(__name__)


class MemoryStatsCache:
    """Process-local TTL cache for ``BillingStats`` rollups.

    Wraps ``cachetools.TTLCache`` with an ``RLock`` (cachetools is not
    thread-safe and the web server is multi-threaded). A daemon cleanup thread
    actively sweeps expired entries so memory does not grow between reads.
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
        self._cache: TTLCache[str, BillingStats] = TTLCache(
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
                name="MemoryStatsCache-cleanup",
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
                self._cache.expire()

    def get(self, key: str) -> BillingStats | None:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: BillingStats) -> None:
        with self._lock:
            self._cache[key] = value

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def close(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._cleanup_thread is not None:
            self._cleanup_thread.join(timeout=2.0)
        self._stop_event = None
        self._cleanup_thread = None
