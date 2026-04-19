from __future__ import annotations

import bcrypt
import structlog

from rentivo.models.user import User
from rentivo.repositories.base import UserRepository

logger = structlog.get_logger(__name__)


class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo

    def create_user(self, username: str, password: str) -> User:
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(username=username, password_hash=password_hash)
        result = self.repo.create(user)
        logger.info("user_created", username=username)
        return result

    def register_user(self, username: str, email: str, password: str) -> User:
        existing = self.repo.get_by_username(username)
        if existing is not None:
            raise ValueError(f"Username '{username}' already exists")
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(username=username, email=email, password_hash=password_hash)
        result = self.repo.create(user)
        logger.info("user_registered", username=username)
        return result

    def get_by_id(self, user_id: int) -> User | None:
        result = self.repo.get_by_id(user_id)
        logger.debug("user_get_by_id", user_id=user_id, found=result is not None)
        return result

    def authenticate(self, username: str, password: str) -> User | None:
        user = self.repo.get_by_username(username)
        if user is None:
            logger.warning("auth_failed", username=username, reason="user_not_found")
            return None
        if bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            logger.info("user_authenticated", username=username)
            return user
        logger.warning("auth_failed", username=username, reason="invalid_password")
        return None

    def change_password(self, username: str, new_password: str) -> None:
        password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        self.repo.update_password_hash(username, password_hash)
        logger.info("password_changed", username=username)

    def list_users(self) -> list[User]:
        result = self.repo.list_all()
        logger.debug("users_listed", count=len(result))
        return result
