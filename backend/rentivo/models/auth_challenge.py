from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AuthChallenge(BaseModel):
    id: int | None = None
    uuid: str = ""
    user_id: int | None
    phase: str
    nonce_hash: bytes = Field(exclude=True, repr=False)
    allowed_methods: tuple[str, ...]
    webauthn_challenge: bytes | None = None
    failures: int = 0
    expires_at: datetime
    created_at: datetime
    consumed_at: datetime | None = None
