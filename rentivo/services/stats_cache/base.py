from __future__ import annotations

from typing import Protocol, runtime_checkable

from rentivo.services.billing_stats import BillingStats


@runtime_checkable
class StatsCache(Protocol):
    """Short-lived cache for ``BillingStats`` rollups, keyed by an opaque string.

    Failure semantics: no method may raise on backend failure. ``get`` returns
    ``None`` on miss or error; ``set`` silently drops on error. The cache is a
    perf layer, never a correctness one.
    """

    def get(self, key: str) -> BillingStats | None:
        """Return the cached value for ``key``, or ``None`` on miss/error."""
        ...

    def set(self, key: str, value: BillingStats) -> None:
        """Store ``value`` under ``key`` with the configured TTL."""
        ...

    def clear(self) -> None:
        """Drop all cached entries (best effort)."""
        ...

    def close(self) -> None:
        """Release any background resources (threads, sockets)."""
        ...
