from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class ItemType(str, Enum):
    FIXED = "fixed"
    VARIABLE = "variable"
    EXTRA = "extra"


class ReadjustmentIndex(str, Enum):
    NONE = "none"
    IGPM = "igpm"
    IPCA = "ipca"


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
    pix_merchant_name: str = ""
    pix_merchant_city: str = ""
    owner_type: str = "user"
    owner_id: int = 0
    items: list[BillingItem] = []
    readjustment_index: ReadjustmentIndex = ReadjustmentIndex.NONE
    readjustment_month: int | None = None  # 1-12 anniversary month, None when not configured
    last_readjustment_date: str | None = None  # ISO YYYY-MM-DD or None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
