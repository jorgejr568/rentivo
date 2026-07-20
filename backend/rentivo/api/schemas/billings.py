from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_EMAIL_LOCAL = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+")
_EMAIL_DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
BillingItemUUID = Annotated[str, Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BillingOwnerRequest(_StrictModel):
    type: Literal["user", "organization"] = "user"
    uuid: str | None = None

    @model_validator(mode="after")
    def valid_reference(self) -> Self:
        if self.type == "organization" and not self.uuid:
            raise ValueError("A organização proprietária é obrigatória.")
        if self.type == "user" and self.uuid is not None:
            raise ValueError("A cobrança pessoal não aceita uma organização.")
        return self


class BillingOwnerResponse(_StrictModel):
    type: Literal["user", "organization"]
    uuid: str | None = None
    name: str | None = None


class BillingItemInput(_StrictModel):
    uuid: BillingItemUUID | None = None
    description: str = Field(min_length=1, max_length=255)
    amount: int = Field(ge=0)
    item_type: Literal["fixed", "variable"]

    @model_validator(mode="after")
    def variable_amount_is_deferred(self) -> Self:
        if self.item_type == "variable" and self.amount != 0:
            raise ValueError("Itens variáveis devem ter valor zero no modelo.")
        return self


class BillingItemResponse(_StrictModel):
    uuid: BillingItemUUID
    description: str
    amount: int
    item_type: Literal["fixed", "variable"]


class ContactInput(_StrictModel):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        if value.count("@") != 1 or any(character.isspace() for character in value):
            raise ValueError("E-mail inválido.")
        local, domain = value.split("@")
        labels = domain.split(".")
        if (
            not local
            or len(local) > 64
            or local.startswith(".")
            or local.endswith(".")
            or ".." in local
            or _EMAIL_LOCAL.fullmatch(local) is None
            or len(domain) > 253
            or len(labels) < 2
            or any(_EMAIL_DOMAIN_LABEL.fullmatch(label) is None for label in labels)
        ):
            raise ValueError("E-mail inválido.")
        return value


class ContactReferenceResponse(_StrictModel):
    uuid: str


class ContactResponse(ContactReferenceResponse):
    name: str
    email: str


class ContactListRequest(_StrictModel):
    items: tuple[ContactInput, ...]


class ContactListResponse(_StrictModel):
    items: tuple[ContactReferenceResponse | ContactResponse, ...]


class BillingCreateRequest(_StrictModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    pix_key: str = ""
    pix_merchant_name: str = Field(default="", max_length=25)
    pix_merchant_city: str = Field(default="", max_length=15)
    owner: BillingOwnerRequest = Field(default_factory=BillingOwnerRequest)
    items: tuple[BillingItemInput, ...] = Field(min_length=1)
    recipients: tuple[ContactInput, ...] | None = None
    reply_to: tuple[ContactInput, ...] | None = None


class BillingUpdateRequest(_StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    pix_key: str | None = None
    pix_merchant_name: str | None = Field(default=None, max_length=25)
    pix_merchant_city: str | None = Field(default=None, max_length=15)
    items: tuple[BillingItemInput, ...] | None = Field(default=None, min_length=1)
    recipients: tuple[ContactInput, ...] | None = None
    reply_to: tuple[ContactInput, ...] | None = None


class BillingCapabilitiesResponse(_StrictModel):
    can_edit: bool
    can_read_bills: bool
    can_create_bills: bool
    can_manage_bills: bool
    can_read_expenses: bool
    can_write_expenses: bool
    can_create_exports: bool
    can_read_attachments: bool
    can_write_attachments: bool
    can_read_theme: bool
    can_manage_theme: bool
    can_upload_bill_receipts: bool
    can_delete: bool
    can_transfer: bool


class CurrentBillResponse(_StrictModel):
    total_amount: int
    status: str
    reference_month: str
    due_date: str | None = None


class BillingStatsResponse(_StrictModel):
    year: int
    expected: int
    received: int
    pending: int
    overdue: int
    paid_count: int
    pending_count: int
    overdue_count: int
    active_count: int
    billed_count: int
    total_expenses: int
    net_income: int


class BillingListItemResponse(_StrictModel):
    uuid: str
    name: str
    description: str
    owner: BillingOwnerResponse
    item_count: int
    pix_needs_setup: bool
    current_bill: CurrentBillResponse | None = None
    capabilities: BillingCapabilitiesResponse


class BillingListResponse(_StrictModel):
    items: tuple[BillingListItemResponse, ...]
    user_pix_incomplete: bool
    stats: BillingStatsResponse


class CommunicationTemplateResponse(_StrictModel):
    comm_type: Literal["bill_ready", "payment_receipt"]
    subject: str
    body: str


class BillingResponse(_StrictModel):
    uuid: str
    name: str
    description: str
    pix_key: str
    pix_merchant_name: str
    pix_merchant_city: str
    owner: BillingOwnerResponse
    items: tuple[BillingItemResponse, ...]
    recipients: tuple[ContactReferenceResponse | ContactResponse, ...]
    reply_to: tuple[ContactReferenceResponse | ContactResponse, ...]
    communication_templates: tuple[CommunicationTemplateResponse, ...]
    stats: BillingStatsResponse
    pix_needs_setup: bool
    capabilities: BillingCapabilitiesResponse
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BillingTransferRequest(_StrictModel):
    organization_uuid: str = Field(min_length=1)


class ExpenseCreateRequest(_StrictModel):
    description: str = Field(min_length=1, max_length=2000)
    amount: int = Field(gt=0)
    category: Literal["iptu", "condominio", "manutencao", "seguro", "outros"]
    incurred_on: date


class ExpenseResponse(_StrictModel):
    uuid: str
    description: str
    amount: int
    category: Literal["iptu", "condominio", "manutencao", "seguro", "outros"]
    incurred_on: date
    created_at: datetime | None = None


class ExpenseListResponse(_StrictModel):
    items: tuple[ExpenseResponse, ...]


class AttachmentResponse(_StrictModel):
    uuid: str
    name: str
    filename: str
    content_type: str
    file_size: int
    sort_order: int
    created_at: datetime | None = None


class AttachmentListResponse(_StrictModel):
    items: tuple[AttachmentResponse, ...]


class ExportCreateRequest(_StrictModel):
    format: Literal["csv", "xlsx"] = "csv"


class ExportCreateResponse(_StrictModel):
    status: Literal["queued"] = "queued"
    format: Literal["csv", "xlsx"]


class CommunicationPreviewRequest(_StrictModel):
    subject: str = ""
    body: str = ""


class CommunicationPreviewResponse(_StrictModel):
    html: str
    severe: tuple[str, ...]
    mild: tuple[str, ...]


class CommunicationSendRequest(_StrictModel):
    bill_uuid: str = Field(min_length=1)
    comm_type: Literal["bill_ready", "payment_receipt"]
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1)
    recipient_uuids: tuple[str, ...] = Field(min_length=1)
    acknowledge_warning: bool = False
    save_scope: Literal["billing", "owner"] | None = None

    @field_validator("recipient_uuids")
    @classmethod
    def distinct_recipients(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Os destinatários devem ser distintos.")
        return value


class CommunicationSendResponse(_StrictModel):
    queued_count: int = Field(ge=0)
