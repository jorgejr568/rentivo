from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class OrgRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    VIEWER = "viewer"

    @classmethod
    def label(cls, value: str) -> str:
        """Return the PT-BR label for a role value, or the raw value as a fallback."""
        return _ROLE_LABELS.get(value, value)


# Module-level so the dict can be imported directly if a caller wants it.
_ROLE_LABELS = {
    OrgRole.ADMIN.value: "Administrador",
    OrgRole.MANAGER.value: "Gerente",
    OrgRole.VIEWER.value: "Visualizador",
    "owner": "Dono",  # not a current OrgRole value but kept for forward-compat with the existing inline dicts
}


class Organization(BaseModel):
    id: int | None = None
    uuid: str = ""
    name: str
    created_by: int | None = None
    enforce_mfa: bool = False
    pix_key: str = ""
    pix_merchant_name: str = ""
    pix_merchant_city: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class OrganizationMember(BaseModel):
    id: int | None = None
    organization_id: int = 0
    user_id: int = 0
    email: str = ""
    role: str = OrgRole.VIEWER.value
    created_at: datetime | None = None
