from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class APIKeyGrantRequest(_StrictModel):
    resource_type: Literal["user", "organization"]
    resource_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_public_workspace_id(self) -> APIKeyGrantRequest:
        if self.resource_type == "user" and self.resource_id != "personal":
            raise ValueError("Personal workspace must use the 'personal' identifier")
        if self.resource_type == "organization" and self.resource_id == "personal":
            raise ValueError("Organization workspace must use its public UUID")
        return self


class APIKeyCreateRequest(_StrictModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: tuple[str, ...] = Field(min_length=1)
    grants: tuple[APIKeyGrantRequest, ...] = Field(min_length=1)
    expires_at: datetime | None = None


class APIKeyUpdateRequest(_StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    scopes: tuple[str, ...] | None = Field(default=None, min_length=1)
    grants: tuple[APIKeyGrantRequest, ...] | None = Field(default=None, min_length=1)

    @model_validator(mode="before")
    @classmethod
    def require_non_null_change(cls, value: Any) -> Any:
        if isinstance(value, dict):
            if not value:
                raise ValueError("At least one API-key field is required")
            if any(field_value is None for field_value in value.values()):
                raise ValueError("API-key fields cannot be null")
        return value


class APIKeyGrantResponse(_StrictModel):
    resource_type: Literal["user", "organization"]
    resource_id: str | None
    available: bool


class APIKeyResponse(_StrictModel):
    uuid: str
    name: str
    hint: str
    scopes: tuple[str, ...]
    grants: tuple[APIKeyGrantResponse, ...]
    expires_at: datetime
    last_used_at: datetime | None
    created_at: datetime
    revoked_at: datetime | None


class APIKeyCreateResponse(APIKeyResponse):
    secret: str


class APIKeyListResponse(_StrictModel):
    items: tuple[APIKeyResponse, ...]


class PersonalWorkspaceOption(_StrictModel):
    resource_type: Literal["user"] = "user"
    resource_id: Literal["personal"] = "personal"


class OrganizationWorkspaceOption(_StrictModel):
    resource_type: Literal["organization"] = "organization"
    resource_id: str
    name: str


class APIKeyOptionsResponse(_StrictModel):
    scopes: tuple[str, ...]
    personal_workspace: PersonalWorkspaceOption
    organizations: tuple[OrganizationWorkspaceOption, ...]
    default_expiration_days: Literal[90] = 90
    max_expiration_days: Literal[365] = 365
