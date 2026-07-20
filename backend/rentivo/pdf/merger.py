"""Merge receipt attachments into the invoice PDF."""

from __future__ import annotations

from io import BytesIO

import structlog
from fpdf import FPDF
from PIL import Image
from pypdf import PdfReader, PdfWriter

from rentivo.observability import traced

logger = structlog.get_logger(__name__)


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

    # Scale to fit while preserving aspect ratio
    scale = min(max_w / width_px, max_h / height_px)
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


def _append_pages(writer: PdfWriter, pdf_bytes: bytes) -> None:
    """Append every page of ``pdf_bytes`` to ``writer``."""
    reader = PdfReader(BytesIO(pdf_bytes))
    for page in reader.pages:
        writer.add_page(page)


@traced("pdf.merge_receipts")
def merge_receipts(
    invoice_pdf: bytes,
    receipts: list[tuple[bytes, str]],
) -> tuple[bytes, list[int]]:
    """Merge receipt attachments after the invoice PDF.

    Args:
        invoice_pdf: The generated invoice PDF bytes.
        receipts: List of (file_bytes, content_type) tuples, in order.

    Returns:
        (merged_pdf_bytes, failed_indices) — failed_indices lists the positions
        in the receipts list that could not be merged.
    """
    if not receipts:
        return invoice_pdf, []

    writer = PdfWriter()
    failed: list[int] = []

    # Add all invoice pages
    try:
        _append_pages(writer, invoice_pdf)
    except Exception:
        logger.exception("invoice_pdf_read_failed")
        return invoice_pdf, list(range(len(receipts)))

    for idx, (file_bytes, content_type) in enumerate(receipts):
        try:
            if content_type == "application/pdf":
                _append_pages(writer, file_bytes)
            elif content_type in ("image/jpeg", "image/png"):
                _append_pages(writer, _image_to_pdf(file_bytes))
            else:
                logger.warning("receipt_merge_skipped_unsupported_type", content_type=content_type)
                failed.append(idx)
        except Exception:
            logger.exception("receipt_merge_failed", content_type=content_type)
            failed.append(idx)
            continue

    output = BytesIO()
    writer.write(output)
    return output.getvalue(), failed
