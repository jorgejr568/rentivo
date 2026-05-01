from unittest.mock import patch

import pytest

from rentivo.email.factory import get_email_backend
from rentivo.email.local import LocalEmailBackend
from rentivo.email.ses import SESEmailBackend
from rentivo.settings import settings


def test_factory_returns_local_backend_by_default():
    backend = get_email_backend()
    assert isinstance(backend, LocalEmailBackend)


def test_factory_returns_ses_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "email_backend", "ses")
    monkeypatch.setattr(settings, "ses_region", "us-east-1")
    monkeypatch.setattr(settings, "ses_access_key_id", "k")
    monkeypatch.setattr(settings, "ses_secret_access_key", "s")
    monkeypatch.setattr(settings, "ses_from_email", "noreply@rentivo.app")
    with patch("rentivo.email.ses.boto3"):
        backend = get_email_backend()
    assert isinstance(backend, SESEmailBackend)


def test_factory_rejects_unknown_backend(monkeypatch):
    monkeypatch.setattr(settings, "email_backend", "carrier-pigeon")
    with pytest.raises(ValueError, match="Unsupported email backend"):
        get_email_backend()


def test_settings_validator_rejects_unknown_backend_at_init(monkeypatch):
    """Sanity: the Settings validator also blocks bad values when constructed fresh."""
    monkeypatch.setenv("RENTIVO_EMAIL_BACKEND", "smoke-signals")
    from rentivo.settings import Settings

    with pytest.raises(ValueError):
        Settings()
