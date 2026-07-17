from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import compare_digest
from typing import NamedTuple

from rentivo.models.auth_challenge import AuthChallenge
from rentivo.observability import traced
from rentivo.repositories.base import AuthChallengeRepository

_DEFAULT_TTL = timedelta(minutes=5)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Authentication challenge datetime requires a timezone offset")
    return value.astimezone(UTC)


class IssuedAuthChallenge(NamedTuple):
    challenge: AuthChallenge
    nonce: str


class AuthChallengeService:
    def __init__(
        self,
        *,
        repository: AuthChallengeRepository,
        now: Callable[[], datetime] = _utcnow,
        token_factory: Callable[[int], str] = secrets.token_urlsafe,
        ttl: timedelta = _DEFAULT_TTL,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("Authentication challenge TTL must be positive")
        self.repository = repository
        self.now = now
        self.token_factory = token_factory
        self.ttl = ttl

    @staticmethod
    def _digest(nonce: str) -> bytes:
        return sha256(nonce.encode()).digest()

    @traced("auth_challenge.issue", record_exception_details=False)
    def issue(
        self,
        *,
        user_id: int | None,
        phase: str,
        allowed_methods: tuple[str, ...],
        webauthn_challenge: bytes | None = None,
    ) -> IssuedAuthChallenge:
        now = _as_aware_utc(self.now())
        nonce = self.token_factory(32)
        challenge = AuthChallenge(
            user_id=user_id,
            phase=phase,
            nonce_hash=self._digest(nonce),
            allowed_methods=allowed_methods,
            webauthn_challenge=webauthn_challenge,
            created_at=now,
            expires_at=now + self.ttl,
        )
        return IssuedAuthChallenge(challenge=self.repository.create(challenge), nonce=nonce)

    @traced("auth_challenge.get_valid", record_exception_details=False)
    def get_valid(
        self,
        uuid: str,
        nonce: str,
        *,
        expected_phase: str,
        expected_method: str | None,
    ) -> AuthChallenge | None:
        challenge = self.repository.get_by_uuid(uuid)
        now = _as_aware_utc(self.now())
        if (
            challenge is None
            or challenge.consumed_at is not None
            or _as_aware_utc(challenge.expires_at) <= now
            or challenge.phase != expected_phase
            or (expected_method is not None and expected_method not in challenge.allowed_methods)
        ):
            return None
        if not compare_digest(challenge.nonce_hash, self._digest(nonce)):
            self.repository.increment_failures(uuid, expected_phase, now)
            return None
        return challenge

    @traced("auth_challenge.record_failure", record_exception_details=False)
    def record_failure(
        self,
        uuid: str,
        nonce: str,
        *,
        expected_phase: str,
        expected_method: str | None,
    ) -> bool:
        challenge = self.get_valid(
            uuid,
            nonce,
            expected_phase=expected_phase,
            expected_method=expected_method,
        )
        if challenge is None:
            return False
        return self.repository.increment_failures(uuid, expected_phase, _as_aware_utc(self.now()))

    @traced("auth_challenge.set_webauthn", record_exception_details=False)
    def set_webauthn_challenge(
        self,
        uuid: str,
        nonce: str,
        *,
        expected_phase: str,
        webauthn_challenge: bytes,
    ) -> AuthChallenge | None:
        challenge = self.get_valid(
            uuid,
            nonce,
            expected_phase=expected_phase,
            expected_method="passkey",
        )
        if challenge is None:
            return None
        updated_at = _as_aware_utc(self.now())
        if not self.repository.set_webauthn_challenge(
            uuid,
            expected_phase,
            webauthn_challenge,
            updated_at,
        ):
            return None
        return challenge.model_copy(update={"webauthn_challenge": webauthn_challenge})

    @traced("auth_challenge.consume", record_exception_details=False)
    def consume(
        self,
        uuid: str,
        nonce: str,
        *,
        expected_phase: str,
        expected_method: str | None,
    ) -> AuthChallenge | None:
        challenge = self.get_valid(
            uuid,
            nonce,
            expected_phase=expected_phase,
            expected_method=expected_method,
        )
        if challenge is None:
            return None
        consumed_at = _as_aware_utc(self.now())
        if not self.repository.consume(uuid, expected_phase, consumed_at):
            return None
        return challenge.model_copy(update={"consumed_at": consumed_at})
