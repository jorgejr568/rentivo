from landlord.models.bill import Bill, BillLineItem
from landlord.models.billing import ItemType
from landlord.pdf.invoice import InvoicePDF
from landlord.pix import generate_pix_qrcode_png


class TestInvoicePDF:
    def _make_bill(self, **overrides):
        defaults = dict(
            id=1,
            uuid="test-uuid",
            billing_id=1,
            reference_month="2025-03",
            total_amount=295000,
            line_items=[
                BillLineItem(
                    description="Aluguel", amount=285000,
                    item_type=ItemType.FIXED, sort_order=0,
                ),
                BillLineItem(
                    description="Água", amount=10000,
                    item_type=ItemType.VARIABLE, sort_order=1,
                ),
            ],
            notes="",
            due_date="10/04/2025",
        )
        defaults.update(overrides)
        return Bill(**defaults)

    def test_generate_returns_pdf_bytes(self):
        pdf_gen = InvoicePDF()
        bill = self._make_bill()
        result = pdf_gen.generate(bill, "Apt 101")

        assert isinstance(result, (bytes, bytearray))
        assert result[:5] == b"%PDF-"

    def test_generate_with_notes(self):
        pdf_gen = InvoicePDF()
        bill = self._make_bill(notes="Test notes here")
        result = pdf_gen.generate(bill, "Apt 101")
        assert result[:5] == b"%PDF-"

    def test_generate_without_due_date(self):
        pdf_gen = InvoicePDF()
        bill = self._make_bill(due_date=None)
        result = pdf_gen.generate(bill, "Apt 101")
        assert result[:5] == b"%PDF-"

    def test_generate_with_pix_page(self):
        pdf_gen = InvoicePDF()
        bill = self._make_bill()
        pix_png = generate_pix_qrcode_png(
            pix_key="test@pix.com",
            merchant_name="Test",
            merchant_city="City",
            amount=2950.00,
        )
        result = pdf_gen.generate(
            bill, "Apt 101",
            pix_qrcode_png=pix_png,
            pix_key="test@pix.com",
            pix_payload="00020126...",
        )
        assert result[:5] == b"%PDF-"
        # With PIX page the PDF should be larger
        assert len(result) > 1000

    def test_generate_without_pix(self):
        pdf_gen = InvoicePDF()
        bill = self._make_bill()
        result = pdf_gen.generate(bill, "Apt 101")
        assert result[:5] == b"%PDF-"
