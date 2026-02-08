from landlord.models.user import User


class TestUser:
    def test_defaults(self):
        user = User(username="admin")
        assert user.id is None
        assert user.password_hash == ""
        assert user.created_at is None

    def test_with_values(self):
        user = User(username="admin", password_hash="hash123", id=1)
        assert user.id == 1
        assert user.password_hash == "hash123"
