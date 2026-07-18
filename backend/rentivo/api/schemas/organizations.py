from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _nonblank(value: str, message: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(message)
    return normalized


class OrganizationCreateRequest(_StrictModel):
    name: str = Field(max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _nonblank(value, "Nome da organização é obrigatório.")


class OrganizationUpdateRequest(_StrictModel):
    name: str | None = Field(default=None, max_length=255)
    pix_key: str | None = None
    pix_merchant_name: str | None = Field(default=None, max_length=25)
    pix_merchant_city: str | None = Field(default=None, max_length=15)

    @model_validator(mode="before")
    @classmethod
    def require_change(cls, value: Any) -> Any:
        if isinstance(value, dict) and (not value or any(item is None for item in value.values())):
            raise ValueError("Informe ao menos uma configuração não nula.")
        return value

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _nonblank(value, "Nome da organização é obrigatório.")

    @field_validator("pix_key", "pix_merchant_name", "pix_merchant_city")
    @classmethod
    def normalize_settings(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class OrganizationMemberUpdateRequest(_StrictModel):
    role: Literal["admin", "manager", "viewer"]


class OrganizationInviteCreateRequest(_StrictModel):
    email: str = Field(max_length=320)
    role: Literal["admin", "manager", "viewer"] = "viewer"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = _nonblank(value, "Informe o e-mail.").lower()
        local, separator, domain = normalized.partition("@")
        if not separator or not local or not domain:
            raise ValueError("Informe um e-mail válido.")
        return normalized


class OrganizationMFAPolicyRequest(_StrictModel):
    enforce_mfa: bool


class BillingTransferRequest(_StrictModel):
    billing_uuid: str = Field(max_length=64)

    @field_validator("billing_uuid")
    @classmethod
    def normalize_billing_uuid(cls, value: str) -> str:
        return _nonblank(value, "Selecione uma cobrança.")


class OrganizationCapabilitiesResponse(_StrictModel):
    can_manage: bool
    can_invite: bool
    can_create_billing: bool


class OrganizationSettingsResponse(_StrictModel):
    pix_key: str
    pix_merchant_name: str
    pix_merchant_city: str


class OrganizationMemberResponse(_StrictModel):
    user_id: int
    email: str
    role: Literal["admin", "manager", "viewer"]
    is_current_user: bool
    created_at: datetime | None


class OrganizationInviteResponse(_StrictModel):
    uuid: str
    invited_email: str
    role: Literal["admin", "manager", "viewer"]
    status: Literal["pending", "accepted", "declined"]
    created_at: datetime | None
    responded_at: datetime | None


class OrganizationResponse(_StrictModel):
    uuid: str
    name: str
    enforce_mfa: bool
    current_role: Literal["admin", "manager", "viewer"]
    capabilities: OrganizationCapabilitiesResponse
    created_at: datetime | None
    updated_at: datetime | None


class OrganizationDetailResponse(OrganizationResponse):
    settings: OrganizationSettingsResponse | None
    members: tuple[OrganizationMemberResponse, ...]
    invites: tuple[OrganizationInviteResponse, ...]


class OrganizationListResponse(_StrictModel):
    items: tuple[OrganizationResponse, ...]


class OrganizationMFAPolicyResponse(_StrictModel):
    enforce_mfa: bool
    mfa_setup_required: bool


class BillingTransferResponse(_StrictModel):
    billing_uuid: str
    organization_uuid: str


class PendingInviteResponse(_StrictModel):
    uuid: str
    organization_uuid: str
    organization_name: str
    invited_by_email: str
    role: Literal["admin", "manager", "viewer"]
    enforce_mfa: bool
    created_at: datetime | None


class PendingInviteListResponse(_StrictModel):
    items: tuple[PendingInviteResponse, ...]


class InviteAcceptResponse(_StrictModel):
    status: Literal["accepted"] = "accepted"
    organization_uuid: str
    mfa_setup_required: bool


class InviteDeclineResponse(_StrictModel):
    status: Literal["declined"] = "declined"
    organization_uuid: str
