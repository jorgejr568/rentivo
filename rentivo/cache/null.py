from __future__ import annotations


class NullKVCache:
    """Cache implementation that does nothing. Selected when
    ``RENTIVO_ENCRYPTION_CACHE_BACKEND=none``."""

    def get_many(self, keys: list[str]) -> dict[str, str]:
        return {}

    def set_many(self, items: dict[str, str]) -> None:
        return None

    def close(self) -> None:
        return None
