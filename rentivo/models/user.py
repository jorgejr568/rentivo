from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class User(BaseModel):
    id: int | None = None
    username: str
    email: str = ""
    password_hash: str = ""
    created_at: datetime | None = None
