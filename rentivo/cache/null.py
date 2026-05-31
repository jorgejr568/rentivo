from __future__ import annotations

from typing import Any


class NullCache:
    """Cache implementation that does nothing. Selected when
    ``RENTIVO_CACHE_BACKEND=none``."""

    def get(self, key: str) -> Any | None:
        return None

    def set(self, key: str, value: Any) -> None:
        return None

    def clear(self) -> None:
        return None

    def close(self) -> None:
        return None
