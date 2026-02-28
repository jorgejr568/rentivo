from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from rentivo.models.billing import ItemType


class BillStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SENT = "sent"
    PAID = "paid"
    CANCELLED = "cancelled"
    DELAYED_PAYMENT = "delayed_payment"


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
    status: str = BillStatus.DRAFT.value
    status_updated_at: datetime | None = None
    created_at: datetime | None = None
    deleted_at: datetime | None = None
