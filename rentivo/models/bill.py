from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from rentivo.constants import SP_TZ
from rentivo.models.billing import ItemType


class BillLineItem(BaseModel):
    id: int | None = None
    bill_id: int | None = None
    description: str
    amount: int  # centavos
    item_type: ItemType
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
    due_date: str | None = None
    paid_at: datetime | None = None
    created_at: datetime | None = None
    deleted_at: datetime | None = None

    @property
    def is_overdue(self) -> bool:
        if self.paid_at is not None:
            return False
        if not self.due_date:
            return False
        try:
            due = datetime.strptime(self.due_date, "%d/%m/%Y").date()
            return datetime.now(SP_TZ).date() > due
        except ValueError:
            return False

    @property
    def payment_status(self) -> str:
        if self.paid_at is not None:
            return "paid"
        if self.is_overdue:
            return "overdue"
        return "pending"
