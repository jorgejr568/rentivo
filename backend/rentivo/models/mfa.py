from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UserTOTP(BaseModel):
    id: int | None = None
    user_id: int = 0
    secret: str = ""
    confirmed: bool = False
    created_at: datetime | None = None
    confirmed_at: datetime | None = None


class RecoveryCode(BaseModel):
    id: int | None = None
    user_id: int = 0
    code_hash: str = ""
    used_at: datetime | None = None
    created_at: datetime | None = None


class UserPasskey(BaseModel):
    id: int | None = None
    uuid: str = ""
    user_id: int = 0
    credential_id: str = ""
    public_key: str = ""
    sign_count: int = 0
    name: str = ""
    transports: str | None = None
    created_at: datetime | None = None
    last_used_at: datetime | None = None
