from __future__ import annotations

from rentivo.services.billing_stats import BillingStats


class NullStatsCache:
    """Cache implementation that does nothing. Selected when
    ``RENTIVO_STATS_CACHE_BACKEND=none``."""

    def get(self, key: str) -> BillingStats | None:
        return None

    def set(self, key: str, value: BillingStats) -> None:
        return None

    def clear(self) -> None:
        return None

    def close(self) -> None:
        return None
