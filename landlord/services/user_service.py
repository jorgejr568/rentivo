from __future__ import annotations

import logging

import bcrypt

from landlord.models.user import User
from landlord.repositories.base import UserRepository

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo

    def create_user(self, username: str, password: str) -> User:
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(username=username, password_hash=password_hash)
        result = self.repo.create(user)
        logger.info("User created: %s", username)
        return result

    def register_user(self, username: str, email: str, password: str) -> User:
        existing = self.repo.get_by_username(username)
        if existing is not None:
            raise ValueError(f"Username '{username}' already exists")
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(username=username, email=email, password_hash=password_hash)
        result = self.repo.create(user)
        logger.info("User registered: %s", username)
        return result

    def get_by_id(self, user_id: int) -> User | None:
        return self.repo.get_by_id(user_id)

    def authenticate(self, username: str, password: str) -> User | None:
        user = self.repo.get_by_username(username)
        if user is None:
            return None
        if bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return user
        return None

    def change_password(self, username: str, new_password: str) -> None:
        password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        self.repo.update_password_hash(username, password_hash)
        logger.info("Password changed for user: %s", username)

    def list_users(self) -> list[User]:
        return self.repo.list_all()
