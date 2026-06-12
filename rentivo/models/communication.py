from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CommunicationTemplate(BaseModel):
    id: int | None = None
    uuid: str = ""
    owner_type: str  # 'user' | 'organization' | 'billing' | 'system'
    owner_id: int
    comm_type: str  # 'bill_ready'
    subject: str
    body_markdown: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Communication(BaseModel):
    id: int | None = None
    uuid: str = ""
    bill_id: int
    comm_type: str  # 'bill_ready'
    recipient_name: str
    recipient_email: str
    subject: str
    body_markdown: str
    status: str = "queued"  # 'queued' | 'sent' | 'failed'
    error: str = ""
    job_ulid: str = ""
    created_at: datetime | None = None
    sent_at: datetime | None = None
