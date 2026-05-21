import pytest
from sqlalchemy import text

from rentivo.models.dashboard import DashboardScope
from rentivo.repositories.dashboard import SQLAlchemyDashboardRepository


@pytest.fixture()
def repo(db_connection):
    from rentivo.encryption.factory import get_encryption

    return SQLAlchemyDashboardRepository(db_connection, get_encryption())


@pytest.fixture()
def encrypt_value():
    from rentivo.encryption.factory import get_encryption

    return get_encryption().encrypt


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


def test_inadimplencia_counts_overdue_unpaid_bills(repo, db_connection):
    _insert_billing(db_connection, billing_id=1, owner_type="user", owner_id=42)
    # overdue + sent → counts
    _insert_bill(db_connection, bill_id=10, billing_id=1, status="sent", amount=5000, month="2026-04", due="2026-04-15")
    # overdue + delayed_payment → counts
    _insert_bill(
        db_connection,
        bill_id=11,
        billing_id=1,
        status="delayed_payment",
        amount=3000,
        month="2026-03",
        due="2026-03-15",
    )
    # overdue but paid → does NOT count
    _insert_bill(db_connection, bill_id=12, billing_id=1, status="paid", amount=9999, month="2026-04", due="2026-04-15")
    # not overdue → does NOT count
    _insert_bill(db_connection, bill_id=13, billing_id=1, status="sent", amount=1234, month="2026-06", due="2026-06-30")
    # no due_date → does NOT count
    _insert_bill(db_connection, bill_id=14, billing_id=1, status="sent", amount=4444, month="2026-04", due=None)
    db_connection.commit()

    inad = repo.inadimplencia(DashboardScope(kind="user", id=42), today="2026-05-20")

    assert inad.amount_cents == 8000
    assert inad.count == 2


def test_monthly_series_groups_by_reference_month(repo, db_connection):
    _insert_billing(db_connection, billing_id=1, owner_type="user", owner_id=42)
    _insert_bill(db_connection, bill_id=10, billing_id=1, status="paid", amount=1000, month="2026-04")
    _insert_bill(db_connection, bill_id=11, billing_id=1, status="paid", amount=2000, month="2026-04")
    _insert_bill(db_connection, bill_id=12, billing_id=1, status="sent", amount=500, month="2026-04")
    _insert_bill(db_connection, bill_id=13, billing_id=1, status="cancelled", amount=99999, month="2026-04")
    _insert_bill(db_connection, bill_id=14, billing_id=1, status="paid", amount=400, month="2026-05")
    db_connection.commit()

    series = repo.monthly_series(DashboardScope(kind="user", id=42), months=["2026-04", "2026-05"])

    by_month = {p.reference_month: p for p in series}
    assert by_month["2026-04"].faturado_cents == 3500
    assert by_month["2026-04"].recebido_cents == 3000
    assert by_month["2026-05"].faturado_cents == 400
    assert by_month["2026-05"].recebido_cents == 400


def test_status_counts_groups_by_status_and_includes_cancelled(repo, db_connection):
    _insert_billing(db_connection, billing_id=1, owner_type="user", owner_id=42)
    _insert_bill(db_connection, bill_id=10, billing_id=1, status="paid", amount=1, month="2026-05")
    _insert_bill(db_connection, bill_id=11, billing_id=1, status="paid", amount=1, month="2026-05")
    _insert_bill(db_connection, bill_id=12, billing_id=1, status="sent", amount=1, month="2026-05")
    _insert_bill(db_connection, bill_id=13, billing_id=1, status="cancelled", amount=1, month="2026-05")
    db_connection.commit()

    counts = repo.status_counts(DashboardScope(kind="user", id=42), reference_month="2026-05")

    by_status = {c.status: c.count for c in counts}
    assert by_status == {"paid": 2, "sent": 1, "cancelled": 1}


def test_top_billings_sorted_desc_limit_5_and_decrypts_names(repo, db_connection, encrypt_value):
    _insert_billing(db_connection, billing_id=1, owner_type="user", owner_id=42)
    _insert_billing(db_connection, billing_id=2, owner_type="user", owner_id=42)
    _insert_billing(db_connection, billing_id=3, owner_type="user", owner_id=42)
    db_connection.execute(
        text("UPDATE billings SET name = :n WHERE id = :id"),
        [
            {"id": 1, "n": encrypt_value("Casa A")},
            {"id": 2, "n": encrypt_value("Casa B")},
            {"id": 3, "n": encrypt_value("Casa C")},
        ],
    )
    _insert_bill(db_connection, bill_id=10, billing_id=1, status="paid", amount=100, month="2026-05")
    _insert_bill(db_connection, bill_id=11, billing_id=2, status="paid", amount=300, month="2026-05")
    _insert_bill(db_connection, bill_id=12, billing_id=3, status="paid", amount=200, month="2026-05")
    db_connection.commit()

    rows = repo.top_billings(DashboardScope(kind="user", id=42), reference_month="2026-05", limit=5)

    assert [r.name for r in rows] == ["Casa B", "Casa C", "Casa A"]
    assert rows[0].faturado_cents == 300
