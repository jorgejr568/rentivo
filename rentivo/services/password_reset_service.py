from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Callable

import structlog

from rentivo.models.password_reset_token import PasswordResetToken
from rentivo.repositories.base import PasswordResetTokenRepository, UserRepository
from rentivo.services.job_service import JobService
from rentivo.services.user_service import UserService

logger = structlog.get_logger(__name__)


class PasswordResetService:
    def __init__(
        self,
        user_repo: UserRepository,
        token_repo: PasswordResetTokenRepository,
        job_service: JobService,
        user_service: UserService,
        public_app_url: str,
        now: Callable[[], datetime] = datetime.utcnow,
        ttl_seconds: int = 3600,
    ) -> None:
        self.user_repo = user_repo
        self.token_repo = token_repo
        self.job_service = job_service
        self.user_service = user_service
        self.public_app_url = public_app_url.rstrip("/")
        self.now = now
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _hash(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    def request_reset(self, email: str) -> str | None:
        user = self.user_repo.get_by_email(email)
        if user is None:
            logger.info("password_reset_unknown_email", email=email)
            return None

        raw = secrets.token_urlsafe(48)
        token = PasswordResetToken(
            user_id=user.id,
            token_hash=self._hash(raw),
            expires_at=self.now() + timedelta(seconds=self.ttl_seconds),
        )
        self.token_repo.create(token)
        reset_url = f"{self.public_app_url}/reset-password?token={raw}"
        self.job_service.enqueue(
            "email.send",
            {
                "event": "password_reset",
                "to_email": user.email,
                "ctx": {"email": user.email, "reset_url": reset_url},
            },
            source="web",
            actor_id=user.id,
            actor_username=user.email,
        )
        logger.info("password_reset_requested", user_id=user.id)
        return raw

    def consume(self, raw_token: str, new_password: str) -> int | None:
        token_hash = self._hash(raw_token)
        token = self.token_repo.get_by_hash(token_hash)
        if token is None:
            logger.warning("password_reset_invalid_token")
            return None
        if token.used_at is not None:
            logger.warning("password_reset_token_already_used", token_id=token.id)
            return None
        if token.expires_at < self.now():
            logger.warning("password_reset_token_expired", token_id=token.id)
            return None

        self.user_service.change_password(token.user_id, new_password)
        self.token_repo.mark_used(token.id)
        self.token_repo.invalidate_all_for_user(token.user_id)
        logger.info("password_reset_completed", user_id=token.user_id)
        return token.user_id
