from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DashboardScope(BaseModel):
    """Identifies whose data a dashboard renders.

    Caching keys are derived from ``kind`` + ``id`` + current reference month.
    """

    kind: Literal["user", "org"]
    id: int

    def cache_key(self, reference_month: str) -> str:
        return f"rentivo:dash:v1:{self.kind}:{self.id}:{reference_month}"


class KPIDelta(BaseModel):
    amount_cents: int
    pct: float | None = None


class KPICard(BaseModel):
    amount_cents: int
    delta: KPIDelta | None = None


class InadimplenciaCard(BaseModel):
    amount_cents: int
    count: int


class CollectionRateCard(BaseModel):
    pct: float | None
    delta_pct: float | None = None


class MonthlyPoint(BaseModel):
    reference_month: str
    faturado_cents: int
    recebido_cents: int


class StatusCount(BaseModel):
    status: str
    count: int


class TopBillingRow(BaseModel):
    uuid: str
    name: str
    faturado_cents: int
    recebido_cents: int
    rate_pct: float | None


class DashboardMetrics(BaseModel):
    reference_month: str
    faturado: KPICard
    recebido: KPICard
    em_aberto: KPICard
    inadimplencia: InadimplenciaCard
    taxa_recebimento: CollectionRateCard
    monthly_series: list[MonthlyPoint] = Field(default_factory=list)
    status_counts: list[StatusCount] = Field(default_factory=list)
    top_billings: list[TopBillingRow] = Field(default_factory=list)
