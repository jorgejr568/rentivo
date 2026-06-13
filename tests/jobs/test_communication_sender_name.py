from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from rentivo.encryption.base64 import Base64Backend
from rentivo.jobs.handlers.communication import _resolve_sender_name
from rentivo.models.billing import Billing
from rentivo.repositories.sqlalchemy.organization import SQLAlchemyOrganizationRepository
from rentivo.repositories.sqlalchemy.user import SQLAlchemyUserRepository
from tests.conftest import SCHEMA_DDL


@pytest.fixture()
def conn():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.connect() as c:
        for stmt in SCHEMA_DDL.strip().split(";"):
            if stmt.strip():
                c.execute(text(stmt))
        c.commit()
        yield c


def _billing(owner_type, owner_id):
    return Billing(id=1, uuid="B", name="Joy 105", owner_type=owner_type, owner_id=owner_id)


def test_org_owned_uses_org_name(conn):
    from rentivo.services.organization_service import OrganizationService

    org = OrganizationService(SQLAlchemyOrganizationRepository(conn, Base64Backend())).create_organization(
        "Imobiliária Aurora", created_by=1
    )
    assert _resolve_sender_name(conn, Base64Backend(), _billing("organization", org.id)) == "Imobiliária Aurora"


def test_user_owned_uses_account_email(conn):
    from rentivo.services.user_service import UserService

    user = UserService(SQLAlchemyUserRepository(conn, Base64Backend())).create_user("jorge@example.com", "pw")
    assert _resolve_sender_name(conn, Base64Backend(), _billing("user", user.id)) == "jorge@example.com"


def test_none_billing_falls_back(conn):
    assert _resolve_sender_name(conn, Base64Backend(), None) == "o responsável"


def test_missing_org_falls_back(conn):
    assert _resolve_sender_name(conn, Base64Backend(), _billing("organization", 9999)) == "o responsável"


def test_missing_user_falls_back(conn):
    assert _resolve_sender_name(conn, Base64Backend(), _billing("user", 9999)) == "o responsável"


def test_handler_threads_org_name_into_sent_email(conn, monkeypatch):
    import rentivo.jobs.handlers.communication as mod
    from rentivo.models.communication import Communication
    from rentivo.repositories.sqlalchemy.communication import SQLAlchemyCommunicationRepository
    from rentivo.services.organization_service import OrganizationService

    org = OrganizationService(SQLAlchemyOrganizationRepository(conn, Base64Backend())).create_organization(
        "Imobiliária Aurora", created_by=1
    )
    conn.execute(
        text(
            "INSERT INTO billings (id, uuid, name, description, pix_key, pix_merchant_name, pix_merchant_city, "
            "owner_type, owner_id, created_at, updated_at) "
            "VALUES (1, 'BU', :n, '', '', '', '', 'organization', :oid, '2026-06-01', '2026-06-01')"
        ),
        {"n": Base64Backend().encrypt("Joy 105"), "oid": org.id},
    )
    conn.execute(
        text(
            "INSERT INTO bills (id, uuid, billing_id, reference_month, total_amount, pdf_path, status, created_at) "
            "VALUES (5, 'BILLUUID', 1, '2026-05', 100000, 'k/bill.pdf', 'published', '2026-05-01')"
        )
    )
    conn.commit()
    comm = SQLAlchemyCommunicationRepository(conn, Base64Backend()).create(
        Communication(
            bill_id=5,
            comm_type="bill_ready",
            recipient_name="Rodrigo",
            recipient_email="rodrigo@example.com",
            subject="Cobrança",
            body_markdown="Prezado Rodrigo",
        )
    )
    sent = {}

    class FakeStorage:
        def get(self, key):
            return b"%PDF"

    class FakeBackend:
        def send(self, message):
            sent["msg"] = message
            return "m-1"

    engine = conn.engine
    monkeypatch.setattr(mod, "get_engine", lambda: engine)
    monkeypatch.setattr(mod, "get_encryption", lambda: Base64Backend())
    monkeypatch.setattr(mod, "get_storage", lambda: FakeStorage())
    monkeypatch.setattr(mod, "get_email_backend", lambda: FakeBackend())

    mod.handle_communication_send({"communication_id": comm.id})
    assert "Imobiliária Aurora" in sent["msg"].html_body
