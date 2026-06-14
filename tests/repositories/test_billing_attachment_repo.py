import pytest

from rentivo.encryption.base64 import Base64Backend
from rentivo.models.billing import Billing
from rentivo.models.billing_attachment import BillingAttachment
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyBillingAttachmentRepository,
    SQLAlchemyBillingRepository,
)


@pytest.fixture()
def billing(db_connection):
    repo = SQLAlchemyBillingRepository(db_connection, Base64Backend())
    return repo.create(Billing(name="Apt 1", items=[]))


def _repo(db_connection):
    return SQLAlchemyBillingAttachmentRepository(db_connection, Base64Backend())


def test_create_and_get_roundtrip(db_connection, billing):
    repo = _repo(db_connection)
    created = repo.create(
        BillingAttachment(
            billing_id=billing.id,
            name="Contrato",
            filename="c.pdf",
            storage_key="k.pdf",
            content_type="application/pdf",
            file_size=4,
        )
    )
    assert created.id is not None
    assert created.uuid != ""
    assert created.name == "Contrato"

    fetched = repo.get_by_uuid(created.uuid)
    assert fetched is not None
    assert fetched.name == "Contrato"
    assert fetched.filename == "c.pdf"
    assert repo.get_by_id(created.id).name == "Contrato"


def test_name_and_filename_encrypted_at_rest(db_connection, billing):
    from sqlalchemy import text

    repo = _repo(db_connection)
    repo.create(
        BillingAttachment(
            billing_id=billing.id,
            name="Contrato",
            filename="c.pdf",
            storage_key="k",
            content_type="application/pdf",
            file_size=1,
        )
    )
    row = db_connection.execute(text("SELECT name, filename FROM billing_attachments")).fetchone()
    assert row[0].startswith("b64:v1:")
    assert row[1].startswith("b64:v1:")


def test_list_by_billing_ordered(db_connection, billing):
    repo = _repo(db_connection)
    for i in range(3):
        repo.create(
            BillingAttachment(
                billing_id=billing.id,
                name=f"n{i}",
                filename=f"f{i}.pdf",
                storage_key=f"k{i}",
                content_type="application/pdf",
                file_size=1,
                sort_order=i,
            )
        )
    items = repo.list_by_billing(billing.id)
    assert [a.name for a in items] == ["n0", "n1", "n2"]


def test_delete(db_connection, billing):
    repo = _repo(db_connection)
    a = repo.create(
        BillingAttachment(
            billing_id=billing.id,
            name="x",
            filename="x.pdf",
            storage_key="k",
            content_type="application/pdf",
            file_size=1,
        )
    )
    repo.delete(a.id)
    assert repo.get_by_uuid(a.uuid) is None


def test_get_missing_returns_none(db_connection):
    repo = _repo(db_connection)
    assert repo.get_by_uuid("nope") is None
    assert repo.get_by_id(999999) is None


def test_list_by_billing_empty_returns_empty(db_connection, billing):
    repo = _repo(db_connection)
    assert repo.list_by_billing(billing.id) == []


def test_create_raises_if_not_retrievable(db_connection, billing, monkeypatch):
    repo = _repo(db_connection)
    monkeypatch.setattr(repo, "get_by_uuid", lambda _uuid: None)
    with pytest.raises(RuntimeError, match="Failed to retrieve attachment"):
        repo.create(
            BillingAttachment(
                billing_id=billing.id,
                name="x",
                filename="x.pdf",
                storage_key="k",
                content_type="application/pdf",
                file_size=1,
            )
        )
