from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

import structlog

from rentivo.models.dashboard import (
    CollectionRateCard,
    DashboardMetrics,
    DashboardScope,
    InadimplenciaCard,
    KPICard,
    KPIDelta,
)
from rentivo.repositories.base import DashboardRepository
from rentivo.services.dashboard_cache import DashboardCache
from rentivo.settings import settings

logger = structlog.get_logger(__name__)


def _previous_month(month: str) -> str:
    """Return the YYYY-MM string for the month before ``month``."""
    year, m = map(int, month.split("-"))
    if m == 1:
        return f"{year - 1}-12"
    return f"{year}-{m - 1:02d}"


def _last_n_months(end_month: str, n: int) -> list[str]:
    months: list[str] = []
    current = end_month
    for _ in range(n):
        months.append(current)
        current = _previous_month(current)
    return list(reversed(months))


def _rate(numer: int, denom: int) -> float | None:
    if denom <= 0:
        return None
    return numer / denom * 100.0


def _compute_delta(current: int, prior: int) -> KPIDelta:
    amount = current - prior
    pct = ((current / prior) - 1.0) * 100.0 if prior > 0 else None
    return KPIDelta(amount_cents=amount, pct=pct)


@dataclass
class DashboardService:
    repository: DashboardRepository
    cache: DashboardCache
    clock: Callable[[], date] = date.today

    def get_metrics(self, scope: DashboardScope) -> DashboardMetrics:
        today = self.clock()
        reference_month = today.strftime("%Y-%m")

        cached = self.cache.get(scope, reference_month)
        if cached is not None:
            return cached

        metrics = self._compute(scope, today, reference_month)
        self.cache.set(scope, metrics)
        return metrics

    def _compute(self, scope: DashboardScope, today: date, reference_month: str) -> DashboardMetrics:
        prior_month = _previous_month(reference_month)
        months = _last_n_months(reference_month, 6)

        current_kpis = self.repository.kpis(scope, reference_month)
        prior_kpis = self.repository.kpis(scope, prior_month)
        inadimplencia = self.repository.inadimplencia(scope, today.strftime("%Y-%m-%d"))
        series = self.repository.monthly_series(scope, months)
        statuses = self.repository.status_counts(scope, reference_month)
        top = self.repository.top_billings(scope, reference_month, limit=5)

        current_rate = _rate(current_kpis.recebido_cents, current_kpis.faturado_cents)
        prior_rate = _rate(prior_kpis.recebido_cents, prior_kpis.faturado_cents)
        delta_rate_pp = current_rate - prior_rate if current_rate is not None and prior_rate is not None else None

        return DashboardMetrics(
            reference_month=reference_month,
            faturado=KPICard(
                amount_cents=current_kpis.faturado_cents,
                delta=_compute_delta(current_kpis.faturado_cents, prior_kpis.faturado_cents),
            ),
            recebido=KPICard(
                amount_cents=current_kpis.recebido_cents,
                delta=_compute_delta(current_kpis.recebido_cents, prior_kpis.recebido_cents),
            ),
            em_aberto=KPICard(amount_cents=current_kpis.em_aberto_cents, delta=None),
            inadimplencia=InadimplenciaCard(amount_cents=inadimplencia.amount_cents, count=inadimplencia.count),
            taxa_recebimento=CollectionRateCard(pct=current_rate, delta_pct=delta_rate_pp),
            monthly_series=series,
            status_counts=statuses,
            top_billings=top,
        )


def get_dashboard_cache() -> DashboardCache:
    """Build a ``DashboardCache`` per ``settings.dashboard_cache_backend``."""
    backend_name = settings.dashboard_cache_backend
    if backend_name == "none":
        from rentivo.cache.null import NullKVCache

        return DashboardCache(NullKVCache())
    if backend_name == "memory":
        from rentivo.cache.memory import MemoryKVCache

        return DashboardCache(
            MemoryKVCache(
                ttl_seconds=settings.dashboard_cache_ttl_seconds,
                max_entries=settings.dashboard_cache_max_entries,
            )
        )
    if backend_name == "redis":
        from rentivo.cache.redis import RedisKVCache

        return DashboardCache(
            RedisKVCache.from_url(
                url=settings.redis_url,
                ttl_seconds=settings.dashboard_cache_ttl_seconds,
            )
        )
    raise ValueError(f"Unsupported dashboard cache backend: {backend_name}")
