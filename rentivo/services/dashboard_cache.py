from __future__ import annotations

import structlog
from pydantic import ValidationError

from rentivo.cache.base import KVCache
from rentivo.models.dashboard import DashboardMetrics, DashboardScope

logger = structlog.get_logger(__name__)


class DashboardCache:
    """JSON-serializing wrapper around a generic ``KVCache``.

    On corrupt / unparseable values the cache silently misses and logs a
    warning; the caller falls back to a fresh compute. Failures must never
    break a dashboard render.
    """

    def __init__(self, backend: KVCache) -> None:
        self._backend = backend

    def get(self, scope: DashboardScope, reference_month: str) -> DashboardMetrics | None:
        key = scope.cache_key(reference_month)
        found = self._backend.get_many([key])
        raw = found.get(key)
        if raw is None:
            return None
        try:
            return DashboardMetrics.model_validate_json(raw)
        except ValidationError:
            logger.warning("dashboard_cache_corrupt_value", key=key)
            return None

    def set(self, scope: DashboardScope, metrics: DashboardMetrics) -> None:
        key = scope.cache_key(metrics.reference_month)
        self._backend.set_many({key: metrics.model_dump_json()})

    def close(self) -> None:
        self._backend.close()
