from rentivo.models.user import User


def test_user_requires_email():
    user = User(email="alice@example.com", password_hash="x")
    assert user.email == "alice@example.com"
    assert not hasattr(user, "username")
