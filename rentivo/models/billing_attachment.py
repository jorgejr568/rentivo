from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BillingAttachment(BaseModel):
    """A named document attached to a billing (e.g. a lease contract).

    Distinct from ``Receipt``: scoped to a ``billing`` (the recurring
    template) rather than a single bill, carries a user-given ``name``
    label, and is never merged into a generated PDF.
    """

    id: int | None = None
    uuid: str = ""
    billing_id: int
    name: str
    filename: str
    storage_key: str = ""
    content_type: str = ""
    file_size: int = 0
    sort_order: int = 0
    created_at: datetime | None = None


ALLOWED_ATTACHMENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_ATTACHMENT_NAME_LENGTH = 255  # cap the user-supplied label before storing
