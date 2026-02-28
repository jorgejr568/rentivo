"""Tests for rentivo.pdf.merger — PDF/image receipt merging."""

from __future__ import annotations

from io import BytesIO

from fpdf import FPDF
from PIL import Image
from pypdf import PdfReader

from rentivo.pdf.merger import _image_to_pdf, merge_receipts


def _make_pdf(num_pages: int = 1) -> bytes:
    """Create a simple test PDF with the given number of pages."""
    pdf = FPDF()
    for i in range(num_pages):
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, f"Page {i + 1}")
    return bytes(pdf.output())


def _make_jpeg() -> bytes:
    """Create a small JPEG test image."""
    img = Image.new("RGB", (200, 300), color="red")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_png() -> bytes:
    """Create a small PNG test image."""
    img = Image.new("RGB", (300, 200), color="blue")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_png_rgba() -> bytes:
    """Create a PNG with alpha channel."""
    img = Image.new("RGBA", (100, 100), color=(0, 255, 0, 128))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_landscape_image() -> bytes:
    """Create a landscape-oriented image (wider than tall)."""
    img = Image.new("RGB", (800, 400), color="green")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestMergeReceipts:
    def test_no_receipts_returns_original(self):
        invoice = _make_pdf(2)
        result = merge_receipts(invoice, [])
        assert result == invoice

    def test_merge_pdf_receipt(self):
        invoice = _make_pdf(1)
        receipt_pdf = _make_pdf(2)
        result = merge_receipts(invoice, [(receipt_pdf, "application/pdf")])
        reader = PdfReader(BytesIO(result))
        assert len(reader.pages) == 3  # 1 invoice + 2 receipt pages

    def test_merge_jpeg_receipt(self):
        invoice = _make_pdf(1)
        jpeg = _make_jpeg()
        result = merge_receipts(invoice, [(jpeg, "image/jpeg")])
        reader = PdfReader(BytesIO(result))
        assert len(reader.pages) == 2  # 1 invoice + 1 image page

    def test_merge_png_receipt(self):
        invoice = _make_pdf(1)
        png = _make_png()
        result = merge_receipts(invoice, [(png, "image/png")])
        reader = PdfReader(BytesIO(result))
        assert len(reader.pages) == 2

    def test_merge_multiple_receipts(self):
        invoice = _make_pdf(1)
        receipts = [
            (_make_pdf(1), "application/pdf"),
            (_make_jpeg(), "image/jpeg"),
            (_make_png(), "image/png"),
        ]
        result = merge_receipts(invoice, receipts)
        reader = PdfReader(BytesIO(result))
        assert len(reader.pages) == 4  # 1 + 1 + 1 + 1

    def test_merge_mixed_types(self):
        invoice = _make_pdf(2)
        receipt_pdf = _make_pdf(3)
        jpeg = _make_jpeg()
        result = merge_receipts(invoice, [(receipt_pdf, "application/pdf"), (jpeg, "image/jpeg")])
        reader = PdfReader(BytesIO(result))
        assert len(reader.pages) == 6  # 2 + 3 + 1

    def test_unsupported_type_skipped(self):
        invoice = _make_pdf(1)
        result = merge_receipts(invoice, [(b"data", "text/plain")])
        reader = PdfReader(BytesIO(result))
        assert len(reader.pages) == 1  # Only invoice

    def test_corrupt_receipt_skipped(self):
        invoice = _make_pdf(1)
        result = merge_receipts(invoice, [(b"not-a-pdf", "application/pdf")])
        reader = PdfReader(BytesIO(result))
        assert len(reader.pages) == 1  # Only invoice, corrupt one skipped

    def test_corrupt_invoice_returns_original(self):
        bad_invoice = b"not-a-pdf"
        result = merge_receipts(bad_invoice, [(_make_pdf(1), "application/pdf")])
        assert result == bad_invoice


class TestImageToPdf:
    def test_portrait_image(self):
        # 200x300 = portrait
        jpeg = _make_jpeg()
        result = _image_to_pdf(jpeg)
        reader = PdfReader(BytesIO(result))
        assert len(reader.pages) == 1
        page = reader.pages[0]
        # Portrait A4: width < height
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        assert height > width

    def test_landscape_image(self):
        jpeg = _make_landscape_image()
        result = _image_to_pdf(jpeg)
        reader = PdfReader(BytesIO(result))
        assert len(reader.pages) == 1
        page = reader.pages[0]
        # Landscape A4: width > height
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        assert width > height

    def test_rgba_image_converted(self):
        png = _make_png_rgba()
        result = _image_to_pdf(png)
        reader = PdfReader(BytesIO(result))
        assert len(reader.pages) == 1

    def test_square_image(self):
        img = Image.new("RGB", (500, 500), color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        result = _image_to_pdf(buf.getvalue())
        reader = PdfReader(BytesIO(result))
        assert len(reader.pages) == 1
