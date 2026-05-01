from unittest.mock import patch

import pytest

from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository


class TestUserRepo:
    def test_create_and_get(self, user_repo: SQLAlchemyUserRepository):
        user = User(email="admin@example.com", password_hash="hash123")
        created = user_repo.create(user)

        assert created.id is not None
        assert created.email == "admin@example.com"
        assert created.password_hash == "hash123"

    def test_get_by_email_returns_user(self, user_repo: SQLAlchemyUserRepository):
        user_repo.create(User(email="alice@example.com", password_hash="x"))
        found = user_repo.get_by_email("alice@example.com")

        assert found is not None
        assert found.email == "alice@example.com"

    def test_get_by_email_returns_none_for_unknown(self, user_repo: SQLAlchemyUserRepository):
        assert user_repo.get_by_email("nobody@example.com") is None

    def test_list_all(self, user_repo: SQLAlchemyUserRepository):
        user_repo.create(User(email="admin1@example.com", password_hash="hash1"))
        user_repo.create(User(email="admin2@example.com", password_hash="hash2"))

        users = user_repo.list_all()
        assert len(users) == 2

    def test_list_all_empty(self, user_repo: SQLAlchemyUserRepository):
        assert user_repo.list_all() == []

    def test_update_password_hash_by_user_id(self, user_repo: SQLAlchemyUserRepository):
        user = user_repo.create(User(email="alice@example.com", password_hash="old"))
        user_repo.update_password_hash(user.id, "new-hash")

        refreshed = user_repo.get_by_id(user.id)
        assert refreshed is not None
        assert refreshed.password_hash == "new-hash"

    def test_get_by_id(self, user_repo: SQLAlchemyUserRepository):
        created = user_repo.create(User(email="admin@example.com", password_hash="hash"))
        fetched = user_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.email == "admin@example.com"

    def test_get_by_id_not_found(self, user_repo: SQLAlchemyUserRepository):
        assert user_repo.get_by_id(9999) is None

    def test_create_runtime_error(self, user_repo: SQLAlchemyUserRepository):
        with patch.object(user_repo, "get_by_email", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve user after create"):
                user_repo.create(User(email="admin@example.com", password_hash="hash"))
