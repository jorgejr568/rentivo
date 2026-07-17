from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256

from rentivo.observability import traced
from rentivo.repositories.base import AuthRateLimitRepository


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RateLimitService:
    def __init__(
        self,
        *,
        repository: AuthRateLimitRepository,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.repository = repository
        self.now = now

    @staticmethod
    def _identity_hash(identity: str) -> bytes:
        return sha256(identity.encode()).digest()

    @traced("auth_rate_limit.reserve", record_exception_details=False)
    def reserve(self, *, action: str, identity: str, limit: int, window_seconds: int) -> bool:
        return self.repository.reserve(
            action=action,
            identity_hash=self._identity_hash(identity),
            limit=limit,
            window_seconds=window_seconds,
            now=self.now(),
        )

    @traced("auth_rate_limit.clear", record_exception_details=False)
    def clear(self, *, action: str, identity: str) -> None:
        self.repository.clear(action=action, identity_hash=self._identity_hash(identity))

    @traced("auth_rate_limit.cleanup", record_exception_details=False)
    def cleanup_expired(self, *, limit: int = 100) -> int:
        return self.repository.delete_expired(cutoff=self.now(), limit=limit)
