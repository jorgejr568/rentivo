from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rentivo.models.bill import BillStatus
from rentivo.models.billing import ItemType


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


Centavos = Annotated[int, Field(strict=True, ge=0)]
PublicIdentifier = Annotated[str, Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")]


def _normalized_description(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("A descrição é obrigatória.")
    return normalized


class BillExtraRequest(_StrictModel):
    description: str = Field(max_length=255)
    amount: Annotated[int, Field(strict=True, gt=0)]

    _normalize_description = field_validator("description")(_normalized_description)


class BillCreateRequest(_StrictModel):
    reference_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    variable_amounts: dict[int, Centavos] = Field(default_factory=dict)
    extras: tuple[BillExtraRequest, ...] = ()
    notes: str = ""
    due_date: date | None = None


class BillLineItemRequest(_StrictModel):
    description: str = Field(max_length=255)
    amount: Centavos
    item_type: ItemType

    _normalize_description = field_validator("description")(_normalized_description)


class BillUpdateRequest(_StrictModel):
    line_items: tuple[BillLineItemRequest, ...] | None = None
    notes: str | None = None
    due_date: date | None = None

    @model_validator(mode="before")
    @classmethod
    def require_change(cls, value: Any) -> Any:
        if isinstance(value, dict) and not value:
            raise ValueError("Ao menos um campo da fatura deve ser informado.")
        return value


class BillTransitionRequest(_StrictModel):
    target: BillStatus
    current_status: BillStatus | None = None


class ReceiptOrderRequest(_StrictModel):
    order: tuple[PublicIdentifier, ...]

    @model_validator(mode="after")
    def require_unique_receipts(self) -> ReceiptOrderRequest:
        if len(set(self.order)) != len(self.order):
            raise ValueError("A ordem dos comprovantes não pode conter duplicatas.")
        return self


class BillLineItemResponse(_StrictModel):
    description: str
    amount: int
    item_type: ItemType
    sort_order: int


class AvailableTransitionResponse(_StrictModel):
    target: str
    label: str
    style: str
    requires_confirmation: bool


class BillCapabilitiesResponse(_StrictModel):
    can_edit: bool
    can_delete: bool
    can_transition: bool
    can_regenerate: bool
    can_upload_receipts: bool
    can_delete_receipts: bool
    can_reorder_receipts: bool
    can_download_invoice: bool
    can_download_recibo: bool


class ReceiptResponse(_StrictModel):
    uuid: str
    filename: str
    content_type: str
    file_size: int
    sort_order: int
    created_at: datetime | None


class RedactedCommunicationHistoryResponse(_StrictModel):
    uuid: str
    comm_type: str
    status: str
    created_at: datetime | None
    sent_at: datetime | None


class CommunicationHistoryResponse(RedactedCommunicationHistoryResponse):
    recipient_name: str
    recipient_email: str
    subject: str


class ReceiptUploadSummary(_StrictModel):
    attached: int = 0
    skipped: int = 0
    total_bytes: int = 0


class BillResponse(_StrictModel):
    uuid: str
    reference_month: str
    total_amount: int
    line_items: tuple[BillLineItemResponse, ...]
    notes: str
    due_date: str | None
    status: str
    status_updated_at: datetime | None
    pdf_render_status: str | None
    created_at: datetime | None
    has_invoice: bool
    has_recibo: bool
    available_transitions: tuple[AvailableTransitionResponse, ...]
    capabilities: BillCapabilitiesResponse


class BillDetailResponse(BillResponse):
    receipts: tuple[ReceiptResponse, ...] = ()
    communications: tuple[CommunicationHistoryResponse | RedactedCommunicationHistoryResponse, ...] = ()
    receipt_upload: ReceiptUploadSummary = Field(default_factory=ReceiptUploadSummary)


class BillListResponse(_StrictModel):
    items: tuple[BillResponse, ...]


class ReceiptListResponse(_StrictModel):
    items: tuple[ReceiptResponse, ...]


class ReceiptUploadResponse(ReceiptUploadSummary):
    items: tuple[ReceiptResponse, ...] = ()
