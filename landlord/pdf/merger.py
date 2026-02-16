"""Merge receipt attachments into the invoice PDF."""

from __future__ import annotations

import logging
from io import BytesIO

from fpdf import FPDF
from PIL import Image
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


def _image_to_pdf(image_bytes: bytes) -> bytes:
    """Convert an image (JPEG/PNG) to a single-page PDF respecting aspect ratio."""
    img = Image.open(BytesIO(image_bytes))

    # Convert RGBA to RGB for PDF compatibility
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    width_px, height_px = img.size

    # Choose orientation based on aspect ratio
    if width_px > height_px:
        orientation = "L"
        page_w, page_h = 297, 210  # A4 landscape in mm
    else:
        orientation = "P"
        page_w, page_h = 210, 297  # A4 portrait in mm

    # Fit image within page with margins
    margin = 10
    max_w = page_w - 2 * margin
    max_h = page_h - 2 * margin

    # Scale to fit
    scale_w = max_w / width_px
    scale_h = max_h / height_px
    scale = min(scale_w, scale_h)

    img_w = width_px * scale
    img_h = height_px * scale

    # Center on page
    x = margin + (max_w - img_w) / 2
    y = margin + (max_h - img_h) / 2

    pdf = FPDF(orientation=orientation, unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=False)

    img_buf = BytesIO()
    img.save(img_buf, format="PNG")
    img_buf.seek(0)

    pdf.image(img_buf, x=x, y=y, w=img_w, h=img_h)

    return bytes(pdf.output())


def merge_receipts(invoice_pdf: bytes, receipts: list[tuple[bytes, str]]) -> bytes:
    """Merge receipt attachments after the invoice PDF.

    Args:
        invoice_pdf: The generated invoice PDF bytes.
        receipts: List of (file_bytes, content_type) tuples, in order.

    Returns:
        Merged PDF bytes.
    """
    if not receipts:
        return invoice_pdf

    writer = PdfWriter()

    # Add all invoice pages
    try:
        invoice_reader = PdfReader(BytesIO(invoice_pdf))
        for page in invoice_reader.pages:
            writer.add_page(page)
    except Exception:
        logger.exception("Failed to read invoice PDF, returning original")
        return invoice_pdf

    # Add each receipt
    for file_bytes, content_type in receipts:
        try:
            if content_type == "application/pdf":
                reader = PdfReader(BytesIO(file_bytes))
                for page in reader.pages:
                    writer.add_page(page)
            elif content_type in ("image/jpeg", "image/png"):
                pdf_bytes = _image_to_pdf(file_bytes)
                reader = PdfReader(BytesIO(pdf_bytes))
                for page in reader.pages:
                    writer.add_page(page)
            else:
                logger.warning("Skipping unsupported content type: %s", content_type)
        except Exception:
            logger.exception("Failed to process receipt (type=%s), skipping", content_type)
            continue

    output = BytesIO()
    writer.write(output)
    return output.getvalue()
