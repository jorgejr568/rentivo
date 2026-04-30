from unittest.mock import patch

import pytest

from rentivo.email.local import LocalEmailBackend
from rentivo.email.ses import SESEmailBackend


def test_factory_returns_local_backend_by_default():
    from rentivo.email.factory import get_email_backend

    backend = get_email_backend()
    assert isinstance(backend, LocalEmailBackend)


def test_factory_returns_ses_when_configured(monkeypatch):
    monkeypatch.setenv("RENTIVO_EMAIL_BACKEND", "ses")
    monkeypatch.setenv("RENTIVO_SES_REGION", "us-east-1")
    monkeypatch.setenv("RENTIVO_SES_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("RENTIVO_SES_SECRET_ACCESS_KEY", "s")
    monkeypatch.setenv("RENTIVO_SES_FROM_EMAIL", "noreply@rentivo.app")
    from importlib import reload

    import rentivo.settings as settings_mod

    reload(settings_mod)
    import rentivo.email.factory as factory_mod

    reload(factory_mod)
    with patch("rentivo.email.ses.boto3"):
        backend = factory_mod.get_email_backend()
    assert isinstance(backend, SESEmailBackend)


def test_factory_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("RENTIVO_EMAIL_BACKEND", "carrier-pigeon")
    from importlib import reload

    import rentivo.settings as settings_mod

    with pytest.raises(ValueError):
        reload(settings_mod)
