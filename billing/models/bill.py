from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BillLineItem(BaseModel):
    id: int | None = None
    bill_id: int | None = None
    description: str
    amount: int  # centavos
    item_type: str  # 'fixed', 'variable', 'extra'
    sort_order: int = 0


class Bill(BaseModel):
    id: int | None = None
    uuid: str = ""
    billing_id: int
    reference_month: str  # 'YYYY-MM'
    total_amount: int = 0  # centavos
    line_items: list[BillLineItem] = []
    pdf_path: str | None = None
    notes: str = ""
    created_at: datetime | None = None
