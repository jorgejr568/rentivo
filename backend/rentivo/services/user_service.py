from __future__ import annotations

import bcrypt
import structlog

from rentivo.models.user import User
from rentivo.observability import span, traced
from rentivo.pix import validate_pix_key
from rentivo.repositories.base import UserAlreadyRegisteredError, UserRepository

logger = structlog.get_logger(__name__)


class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    @traced("user.create_user")
    def create_user(self, email: str, password: str) -> User:
        password_hash = self.hash_password(password)
        user = User(email=email, password_hash=password_hash)
        result = self.repo.create(user)
        logger.info("user_created", email=email)
        return result

    def _reject_if_registered(self, email: str) -> None:
        if self.repo.get_by_email(email) is not None:
            raise UserAlreadyRegisteredError(f"Email '{email}' is already registered")

    @traced("user.register_user")
    def register_user(self, email: str, password: str) -> User:
        self._reject_if_registered(email)
        password_hash = self.hash_password(password)
        user = User(email=email, password_hash=password_hash)
        result = self.repo.create(user)
        logger.info("user_registered", email=email)
        return result

    @traced("user.register_google_user")
    def register_google_user(self, email: str) -> User:
        self._reject_if_registered(email)
        user = User(email=email, password_hash="")
        result = self.repo.create(user)
        logger.info("google_user_registered", email=email)
        return result

    @traced("user.get_by_id")
    def get_by_id(self, user_id: int) -> User | None:
        result = self.repo.get_by_id(user_id)
        logger.debug("user_get_by_id", user_id=user_id, found=result is not None)
        return result

    @traced("user.get_by_email")
    def get_by_email(self, email: str) -> User | None:
        return self.repo.get_by_email(email)

    @traced("user.authenticate")
    def authenticate(self, email: str, password: str) -> User | None:
        user = self.repo.get_by_email(email)
        if user is None:
            logger.warning("auth_failed", email=email, reason="user_not_found")
            return None
        if not user.password_hash:
            logger.warning("auth_failed", email=email, reason="no_password_set")
            return None
        with span("auth.verify_password"):
            password_ok = bcrypt.checkpw(password.encode(), user.password_hash.encode())
        if password_ok:
            logger.info("user_authenticated", email=email)
            return user
        logger.warning("auth_failed", email=email, reason="invalid_password")
        return None

    @traced("user.change_password")
    def change_password(self, user_id: int, new_password: str) -> None:
        password_hash = self.hash_password(new_password)
        self.repo.update_password_hash(user_id, password_hash)
        logger.info("password_changed", user_id=user_id)

    @traced("user.change_password_and_revoke_other_logins")
    def change_password_and_revoke_other_logins(
        self,
        user_id: int,
        new_password: str,
        current_key_uuid: str,
    ) -> int:
        password_hash = self.hash_password(new_password)
        revoked = self.repo.change_password_and_revoke_other_login_tokens(
            user_id,
            password_hash,
            current_key_uuid,
        )
        logger.info("password_changed", user_id=user_id, revoked_other_logins=revoked)
        return revoked

    @traced("user.delete_new_user")
    def delete_new_user(self, user_id: int) -> bool:
        return self.repo.delete(user_id)

    @traced("user.list_users")
    def list_users(self) -> list[User]:
        result = self.repo.list_all()
        logger.debug("users_listed", count=len(result))
        return result

    @traced("user.update_pix")
    def update_pix(
        self,
        user_id: int,
        pix_key: str,
        pix_merchant_name: str,
        pix_merchant_city: str,
    ) -> User:
        normalized_key = validate_pix_key(pix_key) if pix_key.strip() else ""
        self.repo.update_pix(
            user_id,
            normalized_key,
            pix_merchant_name.strip(),
            pix_merchant_city.strip(),
        )
        updated = self.repo.get_by_id(user_id)
        if updated is None:
            raise ValueError("Usuário não encontrado.")
        logger.info("user_pix_updated", user_id=user_id)
        return updated
