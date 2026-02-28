from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class InviteStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class Invite(BaseModel):
    id: int | None = None
    uuid: str = ""
    organization_id: int = 0
    organization_name: str = ""
    invited_user_id: int = 0
    invited_username: str = ""
    invited_by_user_id: int = 0
    invited_by_username: str = ""
    role: str = "viewer"
    status: str = InviteStatus.PENDING.value
    enforce_mfa: bool = False
    created_at: datetime | None = None
    responded_at: datetime | None = None
