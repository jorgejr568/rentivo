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


def rows_to_csv_bytes(headers: list[str], rows: list[list]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def rows_to_xlsx_bytes(headers: list[str], rows: list[list]) -> bytes:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
