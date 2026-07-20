from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class User(BaseModel):
    id: int | None = None
    email: str
    password_hash: str = ""
    pix_key: str = ""
    pix_merchant_name: str = ""
    pix_merchant_city: str = ""
    created_at: datetime | None = None
