from __future__ import annotations


class NullKVCache:
    """Cache implementation that does nothing. Used when caching is disabled
    by configuration."""

    def get_many(self, keys: list[str]) -> dict[str, str]:
        return {}

    def set_many(self, items: dict[str, str]) -> None:
        return None

    def close(self) -> None:
        return None
