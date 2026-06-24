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
            {"name": " João ", "email": " joao@example.com "},
            {"name": "", "email": ""},  # blank — skipped
            {"name": "Ana", "email": "ana@example.com"},
        ],
    )
    rows = service.list_for_billing(1)
    assert [(r.name, r.email) for r in rows] == [
        ("João", "joao@example.com"),
        ("Ana", "ana@example.com"),
    ]


def test_replace_requires_email_for_named_row(service):
    service.replace_for_billing(1, [{"name": "NoEmail", "email": ""}])
    assert service.list_for_billing(1) == []


def test_phone_is_optional_and_trimmed(service):
    service.replace_for_billing(
        1,
        [
            {"name": "João", "email": "joao@example.com", "phone": " +5511999998888 "},
            {"name": "Ana", "email": "ana@example.com"},  # no phone key
            {"name": "Bia", "email": "bia@example.com", "phone": "  "},  # blank -> None
        ],
    )
    rows = service.list_for_billing(1)
    assert [(r.name, r.phone) for r in rows] == [
        ("João", "+5511999998888"),
        ("Ana", None),
        ("Bia", None),
    ]
