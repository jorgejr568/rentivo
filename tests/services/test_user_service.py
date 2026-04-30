from unittest.mock import MagicMock

import bcrypt
import pytest

from rentivo.models.user import User
from rentivo.services.user_service import UserService


class TestUserService:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.service = UserService(self.mock_repo)

    def test_create_user_hashes_password(self):
        self.mock_repo.create.return_value = User(id=1, email="a@b.com", password_hash="hashed")
        result = self.service.create_user("a@b.com", "secret")
        call_args = self.mock_repo.create.call_args[0][0]
        assert call_args.email == "a@b.com"
        assert bcrypt.checkpw(b"secret", call_args.password_hash.encode())
        assert result.email == "a@b.com"

    def test_authenticate_success(self):
        hashed = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode()
        self.mock_repo.get_by_email.return_value = User(id=1, email="a@b.com", password_hash=hashed)
        result = self.service.authenticate("a@b.com", "secret")
        assert result is not None
        assert result.email == "a@b.com"

    def test_authenticate_wrong_password(self):
        hashed = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode()
        self.mock_repo.get_by_email.return_value = User(id=1, email="a@b.com", password_hash=hashed)
        assert self.service.authenticate("a@b.com", "wrong") is None

    def test_authenticate_unknown_email(self):
        self.mock_repo.get_by_email.return_value = None
        assert self.service.authenticate("nobody@b.com", "x") is None

    def test_change_password_updates_hash(self):
        self.service.change_password(42, "new-secret")
        user_id, new_hash = self.mock_repo.update_password_hash.call_args[0]
        assert user_id == 42
        assert bcrypt.checkpw(b"new-secret", new_hash.encode())

    def test_list_users(self):
        self.mock_repo.list_all.return_value = [User(email="a@b.com"), User(email="c@d.com")]
        assert [u.email for u in self.service.list_users()] == ["a@b.com", "c@d.com"]

    def test_get_by_id(self):
        self.mock_repo.get_by_id.return_value = User(id=1, email="a@b.com")
        assert self.service.get_by_id(1).email == "a@b.com"

    def test_get_by_email_returns_user(self):
        self.mock_repo.get_by_email.return_value = User(id=1, email="a@b.com")
        assert self.service.get_by_email("a@b.com").email == "a@b.com"

    def test_register_user_succeeds(self):
        self.mock_repo.get_by_email.return_value = None
        self.mock_repo.create.return_value = User(id=1, email="new@b.com")
        assert self.service.register_user("new@b.com", "pw").email == "new@b.com"

    def test_register_user_duplicate_email(self):
        self.mock_repo.get_by_email.return_value = User(email="dup@b.com")
        with pytest.raises(ValueError):
            self.service.register_user("dup@b.com", "pw")
