from unittest.mock import MagicMock, call

import bcrypt

from landlord.models.user import User
from landlord.services.user_service import UserService


class TestUserService:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.service = UserService(self.mock_repo)

    def test_create_user_hashes_password(self):
        self.mock_repo.create.return_value = User(
            id=1, username="admin", password_hash="hashed"
        )
        result = self.service.create_user("admin", "secret")
        call_args = self.mock_repo.create.call_args[0][0]
        assert call_args.username == "admin"
        # Verify it's a bcrypt hash
        assert call_args.password_hash.startswith("$2b$")
        assert result.username == "admin"

    def test_authenticate_success(self):
        password = "secret"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        self.mock_repo.get_by_username.return_value = User(
            id=1, username="admin", password_hash=hashed
        )
        result = self.service.authenticate("admin", "secret")
        assert result is not None
        assert result.username == "admin"

    def test_authenticate_wrong_password(self):
        hashed = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode()
        self.mock_repo.get_by_username.return_value = User(
            id=1, username="admin", password_hash=hashed
        )
        result = self.service.authenticate("admin", "wrong")
        assert result is None

    def test_authenticate_user_not_found(self):
        self.mock_repo.get_by_username.return_value = None
        result = self.service.authenticate("nonexistent", "pass")
        assert result is None

    def test_change_password(self):
        self.service.change_password("admin", "newpass")
        call_args = self.mock_repo.update_password_hash.call_args
        assert call_args[0][0] == "admin"
        assert call_args[0][1].startswith("$2b$")

    def test_list_users(self):
        self.mock_repo.list_all.return_value = [User(username="a"), User(username="b")]
        result = self.service.list_users()
        assert len(result) == 2
