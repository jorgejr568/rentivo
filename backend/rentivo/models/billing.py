from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel
from ulid import ULID


class ItemType(str, Enum):
    FIXED = "fixed"
    VARIABLE = "variable"
    EXTRA = "extra"


class BillingItem(BaseModel):
    id: int | None = None
    billing_id: int | None = None
    uuid: str = ""
    description: str
    amount: int = 0  # centavos
    item_type: ItemType
    sort_order: int = 0

    def model_post_init(self, __context: object) -> None:
        if not self.uuid:
            self.uuid = str(ULID())


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
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
