from unittest.mock import patch

import pytest

from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository


class TestUserRepo:
    def test_create_and_get(self, user_repo: SQLAlchemyUserRepository):
        user = User(username="admin", password_hash="hash123")
        created = user_repo.create(user)

        assert created.id is not None
        assert created.username == "admin"
        assert created.password_hash == "hash123"

    def test_get_by_username(self, user_repo: SQLAlchemyUserRepository):
        user_repo.create(User(username="admin", password_hash="hash123"))
        fetched = user_repo.get_by_username("admin")

        assert fetched is not None
        assert fetched.username == "admin"

    def test_get_by_username_not_found(self, user_repo: SQLAlchemyUserRepository):
        assert user_repo.get_by_username("nonexistent") is None

    def test_list_all(self, user_repo: SQLAlchemyUserRepository):
        user_repo.create(User(username="admin1", password_hash="hash1"))
        user_repo.create(User(username="admin2", password_hash="hash2"))

        users = user_repo.list_all()
        assert len(users) == 2

    def test_list_all_empty(self, user_repo: SQLAlchemyUserRepository):
        assert user_repo.list_all() == []

    def test_update_password_hash(self, user_repo: SQLAlchemyUserRepository):
        user_repo.create(User(username="admin", password_hash="old_hash"))
        user_repo.update_password_hash("admin", "new_hash")

        fetched = user_repo.get_by_username("admin")
        assert fetched.password_hash == "new_hash"

    def test_get_by_id(self, user_repo: SQLAlchemyUserRepository):
        created = user_repo.create(User(username="admin", password_hash="hash"))
        fetched = user_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.username == "admin"

    def test_get_by_id_not_found(self, user_repo: SQLAlchemyUserRepository):
        assert user_repo.get_by_id(9999) is None

    def test_create_runtime_error(self, user_repo: SQLAlchemyUserRepository):
        with patch.object(user_repo, "get_by_username", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve user after create"):
                user_repo.create(User(username="admin", password_hash="hash"))
