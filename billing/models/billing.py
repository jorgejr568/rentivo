from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class ItemType(str, Enum):
    FIXED = "fixed"
    VARIABLE = "variable"


class BillingItem(BaseModel):
    id: int | None = None
    billing_id: int | None = None
    description: str
    amount: int = 0  # centavos
    item_type: ItemType
    sort_order: int = 0


class Billing(BaseModel):
    id: int | None = None
    uuid: str = ""
    name: str
    description: str = ""
    pix_key: str = ""
    items: list[BillingItem] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
