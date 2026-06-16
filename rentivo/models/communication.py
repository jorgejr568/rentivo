from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class CommType(str, Enum):
    """Communication types. Each maps to a default template
    (rentivo/communications/defaults.py) and the document its send job attaches:
    BILL_READY -> invoice PDF, PAYMENT_RECEIPT -> recibo (payment-receipt) PDF.
    """

    BILL_READY = "bill_ready"
    PAYMENT_RECEIPT = "payment_receipt"


class CommunicationTemplate(BaseModel):
    id: int | None = None
    uuid: str = ""
    owner_type: str  # 'user' | 'organization' | 'billing' | 'system'
    owner_id: int
    comm_type: str  # one of CommType
    subject: str
    body_markdown: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Communication(BaseModel):
    id: int | None = None
    uuid: str = ""
    bill_id: int
    comm_type: str  # one of CommType
    recipient_name: str
    recipient_email: str
    subject: str
    body_markdown: str
    status: str = "queued"  # 'queued' | 'sent' | 'failed'
    error: str = ""
    job_ulid: str = ""
    created_at: datetime | None = None
    sent_at: datetime | None = None
