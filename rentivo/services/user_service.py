from __future__ import annotations

import bcrypt
import structlog

from rentivo.models.user import User
from rentivo.pix import validate_pix_key
from rentivo.repositories.base import UserRepository

logger = structlog.get_logger(__name__)


class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo

    def create_user(self, email: str, password: str) -> User:
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(email=email, password_hash=password_hash)
        result = self.repo.create(user)
        logger.info("user_created", email=email)
        return result

    def register_user(self, email: str, password: str) -> User:
        existing = self.repo.get_by_email(email)
        if existing is not None:
            raise ValueError(f"Email '{email}' is already registered")
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(email=email, password_hash=password_hash)
        result = self.repo.create(user)
        logger.info("user_registered", email=email)
        return result

    def get_by_id(self, user_id: int) -> User | None:
        result = self.repo.get_by_id(user_id)
        logger.debug("user_get_by_id", user_id=user_id, found=result is not None)
        return result

    def get_by_email(self, email: str) -> User | None:
        return self.repo.get_by_email(email)

    def authenticate(self, email: str, password: str) -> User | None:
        user = self.repo.get_by_email(email)
        if user is None:
            logger.warning("auth_failed", email=email, reason="user_not_found")
            return None
        if bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            logger.info("user_authenticated", email=email)
            return user
        logger.warning("auth_failed", email=email, reason="invalid_password")
        return None

    def change_password(self, user_id: int, new_password: str) -> None:
        password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        self.repo.update_password_hash(user_id, password_hash)
        logger.info("password_changed", user_id=user_id)

    def list_users(self) -> list[User]:
        result = self.repo.list_all()
        logger.debug("users_listed", count=len(result))
        return result

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
