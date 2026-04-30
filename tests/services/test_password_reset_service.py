import hashlib
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from rentivo.models.password_reset_token import PasswordResetToken
from rentivo.models.user import User
from rentivo.services.password_reset_service import PasswordResetService


class _Frozen:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _build():
    user_repo = MagicMock()
    token_repo = MagicMock()
    email_service = MagicMock()
    user_service = MagicMock()
    now = datetime(2026, 4, 30, 12, 0, 0)
    service = PasswordResetService(
        user_repo=user_repo,
        token_repo=token_repo,
        email_service=email_service,
        user_service=user_service,
        public_app_url="http://example.com",
        now=_Frozen(now),
        ttl_seconds=3600,
    )
    return service, user_repo, token_repo, email_service, user_service, now


def test_request_reset_with_unknown_email_is_silent_success():
    service, user_repo, token_repo, email_service, _, _ = _build()
    user_repo.get_by_email.return_value = None
    service.request_reset("ghost@example.com")
    token_repo.create.assert_not_called()
    email_service.send_password_recovery.assert_not_called()


def test_request_reset_creates_token_and_sends_email():
    service, user_repo, token_repo, email_service, _, now = _build()
    user_repo.get_by_email.return_value = User(id=1, email="a@b.com")
    raw = service.request_reset("a@b.com")
    assert raw is not None and len(raw) >= 32
    created_token = token_repo.create.call_args[0][0]
    assert created_token.user_id == 1
    assert created_token.token_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert created_token.expires_at == now + timedelta(seconds=3600)
    sent = email_service.send_password_recovery.call_args.kwargs
    assert sent["to_email"] == "a@b.com"
    assert raw in sent["reset_url"]


def test_consume_rejects_unknown_token():
    service, _, token_repo, _, _, _ = _build()
    token_repo.get_by_hash.return_value = None
    assert service.consume("bogus", new_password="np") is None


def test_consume_rejects_expired_token():
    service, _, token_repo, _, _, now = _build()
    token_repo.get_by_hash.return_value = PasswordResetToken(
        id=5, user_id=1, token_hash="h", expires_at=now - timedelta(seconds=1)
    )
    assert service.consume("any", new_password="np") is None


def test_consume_rejects_already_used_token():
    service, _, token_repo, _, _, now = _build()
    token_repo.get_by_hash.return_value = PasswordResetToken(
        id=5, user_id=1, token_hash="h",
        expires_at=now + timedelta(hours=1),
        used_at=now - timedelta(minutes=1),
    )
    assert service.consume("any", new_password="np") is None


def test_consume_resets_password_and_marks_used():
    service, _, token_repo, _, user_service, now = _build()
    raw = "raw-token-value"
    token = PasswordResetToken(
        id=5, user_id=42, token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=now + timedelta(hours=1),
    )
    token_repo.get_by_hash.return_value = token
    user_id = service.consume(raw, new_password="brand-new")
    assert user_id == 42
    user_service.change_password.assert_called_once_with(42, "brand-new")
    token_repo.mark_used.assert_called_once_with(5)
    token_repo.invalidate_all_for_user.assert_called_once_with(42)
