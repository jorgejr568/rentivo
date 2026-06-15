"""Serialize export header + rows into downloadable CSV / XLSX bytes.

Kept separate from ExportService so the row-building logic stays
FastAPI-free and format-agnostic. CSV is emitted as UTF-8 with a BOM so
Excel renders PT-BR accents; XLSX is written to an in-memory buffer via
openpyxl, preserving numeric cells (the ``Valor (R$)`` column) as numbers.
"""

from __future__ import annotations

import csv
import io

import openpyxl

# Leading characters that make a spreadsheet engine treat a cell as a formula.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


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
