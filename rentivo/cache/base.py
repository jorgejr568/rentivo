from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class KVCache(Protocol):
    """Short-lived string key → string value cache.

    Implementations must be safe to call from multiple threads.

    Failure semantics: ``get_many`` and ``set_many`` must never raise on
    backend failure (network errors, decoding failures). On error, return an
    empty dict / silently drop the write and log a warning. The cache is a
    perf layer, never a correctness one.
    """

    def get_many(self, keys: list[str]) -> dict[str, str]:
        """Return the subset of ``keys`` present in the cache, mapped to values."""
        ...

    def set_many(self, items: dict[str, str]) -> None:
        """Store ``items`` (key → value) with the configured TTL."""
        ...

    def close(self) -> None:
        """Release any background resources (threads, sockets)."""
        ...
