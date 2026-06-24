from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Recipient(BaseModel):
    id: int | None = None
    uuid: str = ""
    billing_id: int
    name: str
    email: str
    phone: str | None = None
    sort_order: int = 0
    created_at: datetime | None = None
