from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PasswordResetToken(BaseModel):
    id: int | None = None
    user_id: int
    token_hash: str
    expires_at: datetime
    used_at: datetime | None = None
    created_at: datetime | None = None
