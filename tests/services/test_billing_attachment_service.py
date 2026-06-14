import os

import pytest

from rentivo.models.billing import Billing
from rentivo.models.billing_attachment import MAX_ATTACHMENT_SIZE
from rentivo.services.billing_attachment_service import BillingAttachmentService
from rentivo.storage.local import LocalStorage


class _MemRepo:
    def __init__(self):
        self.rows = []
        self._id = 0

    def create(self, a):
        self._id += 1
        a.id = self._id
        a.uuid = f"u{self._id}"
        self.rows.append(a)
        return a

    def get_by_uuid(self, uuid):
        return next((a for a in self.rows if a.uuid == uuid), None)

    def list_by_billing(self, billing_id):
        return [a for a in self.rows if a.billing_id == billing_id]

    def delete(self, attachment_id):
        self.rows = [a for a in self.rows if a.id != attachment_id]


@pytest.fixture()
def billing():
    return Billing(id=1, uuid="bill-uuid", name="Apt", items=[])


@pytest.fixture()
def service(tmp_path):
    return BillingAttachmentService(_MemRepo(), LocalStorage(str(tmp_path)))


def test_add_attachment_stores_and_persists(service, billing):
    a = service.add_attachment(
        billing, name="Contrato", filename="c.pdf", file_bytes=b"%PDF-x", content_type="application/pdf"
    )
    assert a.id is not None
    assert a.name == "Contrato"
    assert a.storage_key.endswith(".pdf")
    assert "bill-uuid/attachments/" in a.storage_key
    assert service.storage.get(a.storage_key) == b"%PDF-x"


def test_add_attachment_blank_name_defaults_to_filename(service, billing):
    a = service.add_attachment(
        billing, name="   ", filename="lease.pdf", file_bytes=b"%PDF-x", content_type="application/pdf"
    )
    assert a.name == "lease.pdf"


def test_add_attachment_rejects_bad_type(service, billing):
    with pytest.raises(ValueError, match="Unsupported file type"):
        service.add_attachment(billing, name="x", filename="x.gif", file_bytes=b"GIF89a", content_type="image/gif")


def test_add_attachment_rejects_empty(service, billing):
    with pytest.raises(ValueError, match="Empty file"):
        service.add_attachment(billing, name="x", filename="x.pdf", file_bytes=b"", content_type="application/pdf")


def test_add_attachment_rejects_too_large(service, billing):
    with pytest.raises(ValueError, match="File too large"):
        service.add_attachment(
            billing,
            name="x",
            filename="x.pdf",
            file_bytes=b"a" * (MAX_ATTACHMENT_SIZE + 1),
            content_type="application/pdf",
        )


def test_add_attachment_rejects_billing_without_id(service):
    with pytest.raises(ValueError, match="without an id"):
        service.add_attachment(
            Billing(name="x", items=[]),
            name="x",
            filename="x.pdf",
            file_bytes=b"%PDF",
            content_type="application/pdf",
        )


def test_add_attachment_cleans_storage_on_db_failure(service, billing, monkeypatch):
    def boom(_a):
        raise RuntimeError("db down")

    monkeypatch.setattr(service.repo, "create", boom)
    with pytest.raises(RuntimeError, match="db down"):
        service.add_attachment(
            billing, name="x", filename="x.pdf", file_bytes=b"%PDF-x", content_type="application/pdf"
        )
    leftovers = [f for _, _, fs in os.walk(service.storage.base_dir) for f in fs]
    assert leftovers == []


def test_sort_order_increments(service, billing):
    a0 = service.add_attachment(billing, name="a", filename="a.pdf", file_bytes=b"%PDF", content_type="application/pdf")
    a1 = service.add_attachment(billing, name="b", filename="b.pdf", file_bytes=b"%PDF", content_type="application/pdf")
    assert a0.sort_order == 0
    assert a1.sort_order == 1


def test_list_and_get_and_delete(service, billing):
    a = service.add_attachment(billing, name="a", filename="a.pdf", file_bytes=b"%PDF", content_type="application/pdf")
    assert [x.uuid for x in service.list_attachments(billing.id)] == [a.uuid]
    assert service.get_attachment_by_uuid(a.uuid).uuid == a.uuid
    service.delete_attachment(a)
    assert service.list_attachments(billing.id) == []


def test_delete_without_id_raises(service):
    from rentivo.models.billing_attachment import BillingAttachment

    with pytest.raises(ValueError, match="without an id"):
        service.delete_attachment(BillingAttachment(billing_id=1, name="x", filename="x.pdf"))


def test_get_attachment_ref(service, billing):
    a = service.add_attachment(billing, name="a", filename="a.pdf", file_bytes=b"%PDF", content_type="application/pdf")
    ref = service.get_attachment_ref(a)
    assert ref.kind == "local"
    assert ref.location.endswith(".pdf")
