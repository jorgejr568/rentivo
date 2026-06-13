from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from rentivo.encryption.base64 import Base64Backend
from rentivo.repositories.sqlalchemy.recipient import SQLAlchemyRecipientRepository
from rentivo.services.recipient_service import RecipientService
from tests.conftest import SCHEMA_DDL


@pytest.fixture()
def service():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with eng.connect() as c:
        for stmt in SCHEMA_DDL.strip().split(";"):
            if stmt.strip():
                c.execute(text(stmt))
        c.commit()
        yield RecipientService(SQLAlchemyRecipientRepository(c, Base64Backend()))


def test_replace_skips_blank_rows_and_trims(service):
    service.replace_for_billing(
        1,
        [
            {"name": " Rodrigo ", "email": " rodrigo@example.com "},
            {"name": "", "email": ""},  # blank — skipped
            {"name": "Ana", "email": "ana@example.com"},
        ],
    )
    rows = service.list_for_billing(1)
    assert [(r.name, r.email) for r in rows] == [
        ("Rodrigo", "rodrigo@example.com"),
        ("Ana", "ana@example.com"),
    ]


def test_replace_requires_email_for_named_row(service):
    service.replace_for_billing(1, [{"name": "NoEmail", "email": ""}])
    assert service.list_for_billing(1) == []
