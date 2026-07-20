from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class APIKeyGrant(BaseModel, frozen=True):
    resource_type: Literal["user", "organization"]
    resource_id: int


class APIKey(BaseModel):
    id: int | None = None
    uuid: str = ""
    user_id: int
    name: str
    secret_hash: bytes = Field(exclude=True, repr=False)
    key_start: str
    key_end: str
    is_login_token: bool = False
    scopes: frozenset[str] = frozenset()
    grants: tuple[APIKeyGrant, ...] = ()
    expires_at: datetime
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    revoked_at: datetime | None = None
