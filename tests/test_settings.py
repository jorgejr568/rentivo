import pytest
from pydantic import ValidationError

from rentivo.settings import _INSECURE_DEFAULT_KEY, Settings


class TestSettings:
    def test_defaults(self, monkeypatch):
        # Clear any RENTIVO_ env vars that might interfere
        import os

        for key in list(os.environ):
            if key.startswith("RENTIVO_"):
                monkeypatch.delenv(key, raising=False)
        s = Settings(_env_file=None)
        assert s.db_url == "mysql+pymysql://rentivo:rentivo@db:3306/rentivo"
        assert s.storage_backend == "local"
        assert s.storage_prefix == "bills"
        assert s.s3_presigned_expiry == 604800
        assert s.secret_key == _INSECURE_DEFAULT_KEY

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("RENTIVO_DB_URL", "mysql://user:pass@host/db")
        monkeypatch.setenv("RENTIVO_STORAGE_BACKEND", "s3")
        s = Settings(_env_file=None)
        assert s.db_url == "mysql://user:pass@host/db"
        assert s.storage_backend == "s3"

    def test_get_secret_key_generates_random_when_default(self, monkeypatch):
        import os

        for key in list(os.environ):
            if key.startswith("RENTIVO_"):
                monkeypatch.delenv(key, raising=False)
        s = Settings(_env_file=None)
        key = s.get_secret_key()
        assert key != _INSECURE_DEFAULT_KEY
        assert len(key) > 20
        # Second call returns the same generated key
        assert s.get_secret_key() == key

    def test_get_secret_key_uses_custom_when_set(self, monkeypatch):
        monkeypatch.setenv("RENTIVO_SECRET_KEY", "my-production-key")
        s = Settings(_env_file=None)
        assert s.get_secret_key() == "my-production-key"


def test_gtm_container_id_default_is_empty():
    s = Settings(_env_file=None)
    assert s.gtm_container_id == ""


def test_gtm_container_id_accepts_valid():
    s = Settings(_env_file=None, gtm_container_id="GTM-ABC1234")
    assert s.gtm_container_id == "GTM-ABC1234"


def test_gtm_container_id_rejects_invalid_prefix():
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, gtm_container_id="UA-12345")
    assert "must match GTM-[A-Z0-9]+" in str(exc_info.value)


def test_gtm_container_id_rejects_bad_chars():
    """Defense-in-depth: reject any char outside [A-Z0-9] in the suffix."""
    bad_values = [
        "GTM-abc123",  # lowercase
        "GTM-ABC');x()//",  # XSS-style payload
        "GTM-AB C",  # space
        "GTM-AB-C",  # dash
        "GTM-",  # empty suffix
    ]
    for val in bad_values:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, gtm_container_id=val)


def test_environment_default_is_production():
    s = Settings(_env_file=None)
    assert s.environment == "production"


def test_environment_accepts_known_values():
    for value in ("production", "staging", "dev"):
        s = Settings(_env_file=None, environment=value)
        assert s.environment == value


def test_environment_rejects_unknown():
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, environment="qa")
    assert "must be one of" in str(exc_info.value)


def test_settings_email_defaults(monkeypatch):
    for k in (
        "RENTIVO_EMAIL_BACKEND",
        "RENTIVO_SES_REGION",
        "RENTIVO_SES_ACCESS_KEY_ID",
        "RENTIVO_SES_SECRET_ACCESS_KEY",
        "RENTIVO_SES_FROM_EMAIL",
        "RENTIVO_SES_CONFIGURATION_SET",
        "RENTIVO_EMAIL_LOCAL_PATH",
    ):
        monkeypatch.delenv(k, raising=False)
    from rentivo.settings import Settings

    s = Settings()
    assert s.email_backend == "local"
    assert s.email_local_path == "./outbox"
    assert s.ses_region == ""
    assert s.ses_from_email == ""


def test_settings_email_backend_validation(monkeypatch):
    monkeypatch.setenv("RENTIVO_EMAIL_BACKEND", "smoke-signals")
    import pytest as _pytest

    from rentivo.settings import Settings

    with _pytest.raises(ValueError):
        Settings()


def test_settings_turnstile_defaults(monkeypatch):
    for k in ("RENTIVO_TURNSTILE_SITE_KEY", "RENTIVO_TURNSTILE_SECRET_KEY", "RENTIVO_TURNSTILE_VERIFY_URL"):
        monkeypatch.delenv(k, raising=False)
    from rentivo.settings import Settings

    s = Settings()
    assert s.turnstile_site_key == ""
    assert s.turnstile_secret_key == ""
    assert s.turnstile_verify_url == "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def test_settings_turnstile_requires_both_keys(monkeypatch):
    monkeypatch.setenv("RENTIVO_TURNSTILE_SITE_KEY", "1x00000000000000000000AA")
    monkeypatch.delenv("RENTIVO_TURNSTILE_SECRET_KEY", raising=False)
    import pytest as _pytest

    from rentivo.settings import Settings

    with _pytest.raises(ValueError, match="both .* set or both empty"):
        Settings()


def test_settings_turnstile_accepts_paired_keys(monkeypatch):
    monkeypatch.setenv("RENTIVO_TURNSTILE_SITE_KEY", "1x00000000000000000000AA")
    monkeypatch.setenv("RENTIVO_TURNSTILE_SECRET_KEY", "1x0000000000000000000000000000000AA")
    from rentivo.settings import Settings

    s = Settings()
    assert s.turnstile_site_key == "1x00000000000000000000AA"
    assert s.turnstile_secret_key == "1x0000000000000000000000000000000AA"
