from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class OrgRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    VIEWER = "viewer"


class Organization(BaseModel):
    id: int | None = None
    uuid: str = ""
    name: str
    created_by: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class OrganizationMember(BaseModel):
    id: int | None = None
    organization_id: int = 0
    user_id: int = 0
    username: str = ""
    role: str = OrgRole.VIEWER.value
    created_at: datetime | None = None
