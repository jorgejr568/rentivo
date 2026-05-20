import pytest
from sqlalchemy import text

from rentivo.models.dashboard import DashboardScope
from rentivo.repositories.dashboard import SQLAlchemyDashboardRepository


@pytest.fixture()
def repo(db_connection):
    return SQLAlchemyDashboardRepository(db_connection)


def _insert_billing(conn, *, billing_id: int, owner_type: str, owner_id: int) -> None:
    conn.execute(
        text(
            "INSERT INTO billings (id, uuid, name, description, owner_type, owner_id, "
            "pix_key, pix_merchant_name, pix_merchant_city, created_at, updated_at) "
            "VALUES (:id, :uuid, '', '', :ot, :oi, '', '', '', datetime('now'), datetime('now'))"
        ),
        {"id": billing_id, "uuid": f"b-{billing_id}", "ot": owner_type, "oi": owner_id},
    )


def _insert_bill(
    conn, *, bill_id: int, billing_id: int, status: str, amount: int, month: str, due: str | None = None
) -> None:
    conn.execute(
        text(
            "INSERT INTO bills (id, uuid, billing_id, reference_month, total_amount, due_date, "
            "status, status_updated_at, created_at) "
            "VALUES (:id, :uuid, :bid, :rm, :amt, :due, :st, datetime('now'), datetime('now'))"
        ),
        {
            "id": bill_id,
            "uuid": f"bl-{bill_id}",
            "bid": billing_id,
            "rm": month,
            "amt": amount,
            "due": due,
            "st": status,
        },
    )


def test_kpis_user_scope_sums_paid_published_and_excludes_cancelled(repo, db_connection):
    _insert_billing(db_connection, billing_id=1, owner_type="user", owner_id=42)
    _insert_bill(db_connection, bill_id=10, billing_id=1, status="paid", amount=10000, month="2026-05")
    _insert_bill(db_connection, bill_id=11, billing_id=1, status="sent", amount=5000, month="2026-05")
    _insert_bill(db_connection, bill_id=12, billing_id=1, status="cancelled", amount=9999, month="2026-05")
    db_connection.commit()

    kpis = repo.kpis(DashboardScope(kind="user", id=42), reference_month="2026-05")

    assert kpis.faturado_cents == 15000
    assert kpis.recebido_cents == 10000
    assert kpis.em_aberto_cents == 5000


def test_kpis_org_scope_isolates_other_orgs(repo, db_connection):
    _insert_billing(db_connection, billing_id=1, owner_type="organization", owner_id=1)
    _insert_billing(db_connection, billing_id=2, owner_type="organization", owner_id=2)
    _insert_bill(db_connection, bill_id=10, billing_id=1, status="paid", amount=1000, month="2026-05")
    _insert_bill(db_connection, bill_id=11, billing_id=2, status="paid", amount=9999, month="2026-05")
    db_connection.commit()

    kpis = repo.kpis(DashboardScope(kind="org", id=1), reference_month="2026-05")

    assert kpis.recebido_cents == 1000


def test_kpis_zero_when_no_bills(repo, db_connection):
    kpis = repo.kpis(DashboardScope(kind="user", id=9999), reference_month="2026-05")
    assert kpis.faturado_cents == 0
    assert kpis.recebido_cents == 0
    assert kpis.em_aberto_cents == 0
