from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from rentivo.models.billing import ItemType


class BillStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SENT = "sent"
    PAID = "paid"
    CANCELLED = "cancelled"
    DELAYED_PAYMENT = "delayed_payment"


# Canonical bill status lifecycle: rascunho → publicado → enviado → pago, with
# cancel from any active state and reopen-from-cancelled. This is the single
# source of truth for *which* transitions are permitted. It is enforced
# server-side in ``BillService.change_status`` (defense-in-depth) and mirrored by
# the UI affordance policy in ``web/bill_transitions.py`` — a consistency test
# keeps the two from drifting (see tests/web/test_bill_transitions.py).
ALLOWED_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    BillStatus.DRAFT.value: frozenset({BillStatus.PUBLISHED.value, BillStatus.SENT.value, BillStatus.CANCELLED.value}),
    BillStatus.PUBLISHED.value: frozenset(
        {
            BillStatus.SENT.value,
            BillStatus.PAID.value,
            BillStatus.DRAFT.value,
            BillStatus.CANCELLED.value,
        }
    ),
    BillStatus.SENT.value: frozenset(
        {
            BillStatus.PAID.value,
            BillStatus.DELAYED_PAYMENT.value,
            BillStatus.PUBLISHED.value,
            BillStatus.CANCELLED.value,
        }
    ),
    BillStatus.DELAYED_PAYMENT.value: frozenset(
        {BillStatus.PAID.value, BillStatus.SENT.value, BillStatus.CANCELLED.value}
    ),
    BillStatus.PAID.value: frozenset({BillStatus.SENT.value, BillStatus.CANCELLED.value}),
    BillStatus.CANCELLED.value: frozenset({BillStatus.DRAFT.value}),
}


class InvalidStatusTransition(ValueError):
    """Raised when a bill status change is not permitted by the lifecycle.

    Subclasses ``ValueError`` so existing ``except ValueError`` callers still
    treat it as a rejected change, while callers that want a transition-specific
    message (e.g. the change-status route) can catch it explicitly first.
    """

    def __init__(self, current: str, new: str) -> None:
        self.current = current
        self.new = new
        super().__init__(f"Transition {current!r} -> {new!r} is not allowed")


def is_transition_allowed(current: str, new: str) -> bool:
    """Return whether moving a bill from ``current`` to ``new`` status is allowed.

    A no-op (``current == new``) is treated as allowed and idempotent. Any other
    move must appear in :data:`ALLOWED_STATUS_TRANSITIONS`; unknown source
    statuses offer no transitions.
    """

    if current == new:
        return True
    return new in ALLOWED_STATUS_TRANSITIONS.get(current, frozenset())


class BillLineItem(BaseModel):
    id: int | None = None
    bill_id: int | None = None
    description: str
    amount: int  # centavos
    item_type: ItemType
    sort_order: int = 0


class BillSummary(BaseModel):
    """Lightweight scalar view of a bill — no line items, no decryption.

    Used to compute dashboard / organization KPI rollups without hydrating
    every bill's encrypted notes and line items.
    """

    billing_id: int
    total_amount: int = 0  # centavos
    status: str = BillStatus.DRAFT.value
    reference_month: str = ""
    due_date: str | None = None


class Bill(BaseModel):
    id: int | None = None
    uuid: str = ""
    billing_id: int
    reference_month: str  # 'YYYY-MM'
    total_amount: int = 0  # centavos
    line_items: list[BillLineItem] = []
    pdf_path: str | None = None
    recibo_pdf_path: str | None = None
    notes: str = ""
    due_date: str | None = None
    status: str = BillStatus.DRAFT.value
    status_updated_at: datetime | None = None
    pdf_render_status: str | None = None
    mutation_revision: int = 0
    created_at: datetime | None = None
    deleted_at: datetime | None = None
