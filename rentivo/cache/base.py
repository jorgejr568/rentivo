from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Cache(Protocol):
    """Short-lived key→value cache.

    Values must be JSON-serialisable (dict / list / str / int / float / bool /
    None) so the Redis backend can persist them; the in-memory backend stores
    them as-is.

    Failure semantics: no method may raise on backend failure. ``get`` returns
    ``None`` on miss or error; ``set`` silently drops on error. The cache is a
    perf layer, never a correctness one.
    """

    def get(self, key: str) -> Any | None:
        """Return the cached value for ``key``, or ``None`` on miss/error."""
        ...

    def set(self, key: str, value: Any) -> None:
        """Store ``value`` under ``key`` with the configured TTL."""
        ...

    def clear(self) -> None:
        """Drop all cached entries (best effort)."""
        ...

    def close(self) -> None:
        """Release any background resources (threads, sockets)."""
        ...
