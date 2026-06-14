from rentivo.models.billing_attachment import (
    ALLOWED_ATTACHMENT_TYPES,
    MAX_ATTACHMENT_NAME_LENGTH,
    MAX_ATTACHMENT_SIZE,
    BillingAttachment,
)


def test_defaults():
    a = BillingAttachment(billing_id=1, name="Contrato", filename="contrato.pdf")
    assert a.id is None
    assert a.uuid == ""
    assert a.billing_id == 1
    assert a.name == "Contrato"
    assert a.filename == "contrato.pdf"
    assert a.storage_key == ""
    assert a.content_type == ""
    assert a.file_size == 0
    assert a.sort_order == 0
    assert a.created_at is None


def test_constants():
    assert ALLOWED_ATTACHMENT_TYPES == {"application/pdf", "image/jpeg", "image/png"}
    assert MAX_ATTACHMENT_SIZE == 10 * 1024 * 1024
    assert MAX_ATTACHMENT_NAME_LENGTH == 255
