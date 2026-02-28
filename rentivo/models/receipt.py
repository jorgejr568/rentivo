from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Receipt(BaseModel):
    id: int | None = None
    uuid: str = ""
    bill_id: int
    filename: str
    storage_key: str = ""
    content_type: str = ""
    file_size: int = 0
    sort_order: int = 0
    created_at: datetime | None = None


ALLOWED_RECEIPT_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_RECEIPT_SIZE = 10 * 1024 * 1024  # 10 MB
