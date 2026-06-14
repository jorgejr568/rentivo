"""Unit tests for ExportService — backend-agnostic row building."""

from __future__ import annotations

from datetime import datetime

from rentivo.models.bill import Bill, BillStatus
from rentivo.models.billing import Billing
from rentivo.services.export_service import ExportService


def _billing() -> Billing:
    return Billing(id=1, uuid="bil-u", name="Apt 101")


def _bill(**overrides) -> Bill:
    defaults = dict(
        id=1,
        uuid="bill-u",
        billing_id=1,
        reference_month="2025-03",
        total_amount=285050,
        due_date="10/04/2025",
        status=BillStatus.PAID.value,
        status_updated_at=datetime(2025, 4, 9, 14, 30),
    )
    defaults.update(overrides)
    return Bill(**defaults)


class TestBuildRows:
    def test_headers_are_pt_br(self):
        assert ExportService().HEADERS == [
            "Mês de referência",
            "Cobrança",
            "Valor (R$)",
            "Valor formatado",
            "Status",
            "Vencimento",
            "Pago/Atualizado em",
        ]

    def test_row_values(self):
        rows = ExportService().build_rows(_billing(), [_bill()])
        assert rows == [
            [
                "Março/2025",
                "Apt 101",
                2850.50,
                "R$ 2.850,50",
                "Pago",
                "10/04/2025",
                "09/04/2025 14:30",
            ]
        ]

    def test_amount_column_is_numeric_float(self):
        rows = ExportService().build_rows(_billing(), [_bill()])
        assert isinstance(rows[0][2], float)

    def test_unknown_status_falls_back_to_raw_value(self):
        rows = ExportService().build_rows(_billing(), [_bill(status="weird")])
        assert rows[0][4] == "weird"

    def test_missing_optional_fields_render_empty(self):
        rows = ExportService().build_rows(_billing(), [_bill(due_date=None, status_updated_at=None)])
        assert rows[0][5] == ""
        assert rows[0][6] == ""

    def test_empty_bill_list_yields_no_rows(self):
        assert ExportService().build_rows(_billing(), []) == []
