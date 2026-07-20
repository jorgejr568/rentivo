from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class KnownDevice(BaseModel):
    id: int | None = None
    user_id: int
    device_hash: str
    user_agent_snippet: str = ""
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
