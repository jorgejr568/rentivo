from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from rentivo.models.dashboard import DashboardScope, MonthlyPoint, StatusCount
from rentivo.repositories.base import DashboardKPIs, DashboardRepository, InadimplenciaResult

_USER_SCOPE_SQL = (
    "(owner_type = 'user' AND owner_id = :scope_id) OR "
    "(owner_type = 'organization' AND owner_id IN "
    "(SELECT organization_id FROM organization_members WHERE user_id = :scope_id))"
)

_ORG_SCOPE_SQL = "owner_type = 'organization' AND owner_id = :scope_id"


def _scope_where(scope: DashboardScope) -> str:
    return _USER_SCOPE_SQL if scope.kind == "user" else _ORG_SCOPE_SQL


class SQLAlchemyDashboardRepository(DashboardRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def kpis(self, scope: DashboardScope, reference_month: str) -> DashboardKPIs:
        row = (
            self.conn.execute(
                text(
                    "SELECT "
                    "COALESCE(SUM(CASE WHEN b.status != 'cancelled' THEN b.total_amount END), 0) AS faturado, "
                    "COALESCE(SUM(CASE WHEN b.status = 'paid' THEN b.total_amount END), 0) AS recebido, "
                    "COALESCE(SUM(CASE WHEN b.status IN ('published', 'sent', 'delayed_payment') "
                    "THEN b.total_amount END), 0) AS em_aberto "
                    "FROM bills b "
                    "JOIN billings bg ON b.billing_id = bg.id "
                    f"WHERE b.deleted_at IS NULL AND bg.deleted_at IS NULL "
                    f"AND b.reference_month = :reference_month AND ({_scope_where(scope)})"
                ),
                {"scope_id": scope.id, "reference_month": reference_month},
            )
            .mappings()
            .fetchone()
        )
        return DashboardKPIs(
            faturado_cents=int(row["faturado"]),
            recebido_cents=int(row["recebido"]),
            em_aberto_cents=int(row["em_aberto"]),
        )

    def inadimplencia(self, scope: DashboardScope, today: str) -> InadimplenciaResult:
        row = (
            self.conn.execute(
                text(
                    "SELECT COALESCE(SUM(b.total_amount), 0) AS amt, COUNT(*) AS cnt "
                    "FROM bills b JOIN billings bg ON b.billing_id = bg.id "
                    "WHERE b.deleted_at IS NULL AND bg.deleted_at IS NULL "
                    "AND b.status IN ('sent', 'delayed_payment') "
                    "AND b.due_date IS NOT NULL AND b.due_date < :today "
                    f"AND ({_scope_where(scope)})"
                ),
                {"scope_id": scope.id, "today": today},
            )
            .mappings()
            .fetchone()
        )
        return InadimplenciaResult(amount_cents=int(row["amt"]), count=int(row["cnt"]))

    def monthly_series(self, scope: DashboardScope, months: list[str]) -> list[MonthlyPoint]:
        if not months:
            return []
        from sqlalchemy import bindparam

        stmt = text(
            "SELECT b.reference_month, "
            "COALESCE(SUM(CASE WHEN b.status != 'cancelled' THEN b.total_amount END), 0) AS faturado, "
            "COALESCE(SUM(CASE WHEN b.status = 'paid' THEN b.total_amount END), 0) AS recebido "
            "FROM bills b JOIN billings bg ON b.billing_id = bg.id "
            "WHERE b.deleted_at IS NULL AND bg.deleted_at IS NULL "
            "AND b.reference_month IN :months "
            f"AND ({_scope_where(scope)}) "
            "GROUP BY b.reference_month"
        ).bindparams(bindparam("months", expanding=True))

        rows = self.conn.execute(stmt, {"scope_id": scope.id, "months": months}).mappings().fetchall()
        return [
            MonthlyPoint(
                reference_month=row["reference_month"],
                faturado_cents=int(row["faturado"]),
                recebido_cents=int(row["recebido"]),
            )
            for row in rows
        ]

    def status_counts(self, scope: DashboardScope, reference_month: str) -> list[StatusCount]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT b.status AS status, COUNT(*) AS cnt "
                    "FROM bills b JOIN billings bg ON b.billing_id = bg.id "
                    "WHERE b.deleted_at IS NULL AND bg.deleted_at IS NULL "
                    "AND b.reference_month = :reference_month "
                    f"AND ({_scope_where(scope)}) "
                    "GROUP BY b.status"
                ),
                {"scope_id": scope.id, "reference_month": reference_month},
            )
            .mappings()
            .fetchall()
        )
        return [StatusCount(status=row["status"], count=int(row["cnt"])) for row in rows]
