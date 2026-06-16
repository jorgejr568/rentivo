"""Serialize export header + rows into downloadable CSV / XLSX bytes.

Kept separate from ExportService so the row-building logic stays
FastAPI-free and format-agnostic. CSV is emitted as UTF-8 with a BOM so
Excel renders PT-BR accents; XLSX is written to an in-memory buffer via
openpyxl, preserving numeric cells (the ``Valor (R$)`` column) as numbers.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata

import openpyxl

# Leading characters that make a spreadsheet engine treat a cell as a formula.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")

# Media types for the two supported export formats. The CSV one carries a
# charset for HTTP responses; the worker strips it for the MIME attachment part.
CSV_CONTENT_TYPE = "text/csv; charset=utf-8"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _neutralize(value):
    """Prefix string cells that could be parsed as a formula with a single quote.

    Mitigates CSV/spreadsheet formula injection: a value like ``=cmd|calc!A1``
    can execute when opened in Excel/Sheets. Non-string cells (e.g. the numeric
    reais amount) pass through untouched so XLSX keeps them as numbers.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_TRIGGERS):
        return "'" + value
    return value


def rows_to_csv_bytes(headers: list[str], rows: list[list]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows([_neutralize(cell) for cell in row] for row in rows)
    return buffer.getvalue().encode("utf-8-sig")


def rows_to_xlsx_bytes(headers: list[str], rows: list[list]) -> bytes:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append([_neutralize(cell) for cell in row])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def serialize_rows(fmt: str, headers: list[str], rows: list[list]) -> tuple[bytes, str, str]:
    """Serialize header + rows for the requested format.

    Returns ``(body, content_type, ext)``. ``fmt`` is matched
    case-insensitively; anything other than ``xlsx`` falls back to CSV so an
    unknown/typo value still yields a usable file instead of an error.
    """
    if (fmt or "").strip().lower() == "xlsx":
        return rows_to_xlsx_bytes(headers, rows), XLSX_CONTENT_TYPE, "xlsx"
    return rows_to_csv_bytes(headers, rows), CSV_CONTENT_TYPE, "csv"


def export_slug(name: str) -> str:
    """Lowercase ASCII slug for an export filename (PT-BR name → safe slug).

    Unicode-normalizes (NFKD) and drops combining marks so accented characters
    transliterate (``ã``→``a``, ``ç``→``c``, ``í``→``i``) instead of being
    stripped. Stays injection-safe: the result only ever contains ``[a-z0-9-]``.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or "cobranca"


def export_filename(billing_name: str, ext: str) -> str:
    """Build the download filename for a billing's bill export (``faturas_<slug>.<ext>``)."""
    return f"faturas_{export_slug(billing_name)}.{ext}"
