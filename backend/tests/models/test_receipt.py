from rentivo.models.receipt import ALLOWED_RECEIPT_TYPES, MAX_RECEIPT_SIZE, Receipt


class TestReceipt:
    def test_construction(self):
        receipt = Receipt(bill_id=1, filename="receipt.pdf")
        assert receipt.id is None
        assert receipt.uuid == ""
        assert receipt.bill_id == 1
        assert receipt.filename == "receipt.pdf"
        assert receipt.storage_key == ""
        assert receipt.content_type == ""
        assert receipt.file_size == 0
        assert receipt.sort_order == 0
        assert receipt.created_at is None

    def test_full_construction(self):
        receipt = Receipt(
            id=5,
            uuid="abc123",
            bill_id=10,
            filename="photo.jpg",
            storage_key="billing/bill/receipts/abc123.jpg",
            content_type="image/jpeg",
            file_size=1024,
            sort_order=2,
        )
        assert receipt.id == 5
        assert receipt.uuid == "abc123"
        assert receipt.content_type == "image/jpeg"
        assert receipt.file_size == 1024
        assert receipt.sort_order == 2


class TestConstants:
    def test_allowed_types(self):
        assert "application/pdf" in ALLOWED_RECEIPT_TYPES
        assert "image/jpeg" in ALLOWED_RECEIPT_TYPES
        assert "image/png" in ALLOWED_RECEIPT_TYPES
        assert "image/gif" not in ALLOWED_RECEIPT_TYPES

    def test_max_size(self):
        assert MAX_RECEIPT_SIZE == 10 * 1024 * 1024
