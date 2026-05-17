from __future__ import annotations

import threading
import time
from typing import Callable

import structlog
from cachetools import TTLCache

logger = structlog.get_logger(__name__)


class MemoryDecryptCache:
    """Process-local TTL cache for decrypted plaintexts.

    Wraps ``cachetools.TTLCache`` with an ``RLock`` because ``cachetools`` is
    not thread-safe and KMS ``decrypt_many`` fans out via a thread pool.

    A daemon cleanup thread (added in a later commit) actively sweeps expired
    entries so memory does not grow unbounded between reads.
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
        # Cleanup thread fields — populated in a later commit.
        self._stop_event: threading.Event | None = None
        self._cleanup_thread: threading.Thread | None = None

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
        # Cleanup thread shutdown is added in a later commit; no-op for now.
        return None
