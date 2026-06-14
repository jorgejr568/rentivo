"""Backend-agnostic export row building for a billing's bills.

ExportService turns a Billing + its bills into a header row and plain-Python
data rows. It has no FastAPI / HTTP dependency so it can be unit-tested in
isolation; the route layer serializes the rows into CSV or XLSX bytes.

The primary amount column (``Valor (R$)``) is a numeric ``float`` in reais
(centavos / 100) so accountants can sum it in a spreadsheet. A separate
``Valor formatado`` column carries the human-readable ``R$ ...`` string.
"""

from __future__ import annotations

from rentivo.constants import STATUS_LABELS, format_month
from rentivo.models import format_brl
from rentivo.models.bill import Bill, BillStatus
from rentivo.models.billing import Billing

HEADERS = [
    "Mês de referência",
    "Cobrança",
    "Valor (R$)",
    "Valor formatado",
    "Status",
    "Vencimento",
    "Pago/Atualizado em",
]


def _status_label(status: str) -> str:
    try:
        return STATUS_LABELS[BillStatus(status)]
    except ValueError:
        return status


class ExportService:
    """Build header + data rows for a billing's bills (FastAPI-free)."""

    HEADERS = HEADERS

    def build_rows(self, billing: Billing, bills: list[Bill]) -> list[list]:
        rows: list[list] = []
        for bill in bills:
            updated = bill.status_updated_at.strftime("%d/%m/%Y %H:%M") if bill.status_updated_at else ""
            rows.append(
                [
                    format_month(bill.reference_month),
                    billing.name,
                    bill.total_amount / 100,
                    format_brl(bill.total_amount),
                    _status_label(bill.status),
                    bill.due_date or "",
                    updated,
                ]
            )
        return rows
