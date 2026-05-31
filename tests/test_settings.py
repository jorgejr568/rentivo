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


def test_default_job_worker_settings():
    from rentivo.settings import Settings

    s = Settings(_env_file=None)
    assert s.job_worker_batch_size == 10
    assert s.job_worker_idle_sleep_seconds == 5.0
    assert s.job_worker_stuck_after_seconds == 600


def test_job_worker_settings_overrides_via_env(monkeypatch):
    monkeypatch.setenv("RENTIVO_JOB_WORKER_BATCH_SIZE", "25")
    monkeypatch.setenv("RENTIVO_JOB_WORKER_IDLE_SLEEP_SECONDS", "1.5")
    monkeypatch.setenv("RENTIVO_JOB_WORKER_STUCK_AFTER_SECONDS", "120")

    from rentivo.settings import Settings

    s = Settings(_env_file=None)
    assert s.job_worker_batch_size == 25
    assert s.job_worker_idle_sleep_seconds == 1.5
    assert s.job_worker_stuck_after_seconds == 120


def test_encryption_backend_default_is_base64(monkeypatch):
    import os

    for key in list(os.environ):
        if key.startswith("RENTIVO_"):
            monkeypatch.delenv(key, raising=False)
    from rentivo.settings import Settings

    s = Settings(_env_file=None)
    assert s.encryption_backend == "base64"
    assert s.kms_key_id == ""
    assert s.kms_region == ""


def test_encryption_backend_accepts_kms_when_configured(monkeypatch):
    monkeypatch.setenv("RENTIVO_ENCRYPTION_BACKEND", "kms")
    monkeypatch.setenv("RENTIVO_KMS_KEY_ID", "alias/rentivo")
    monkeypatch.setenv("RENTIVO_KMS_REGION", "us-east-1")
    from rentivo.settings import Settings

    s = Settings(_env_file=None)
    assert s.encryption_backend == "kms"
    assert s.kms_key_id == "alias/rentivo"
    assert s.kms_region == "us-east-1"


def test_encryption_backend_rejects_unknown(monkeypatch):
    monkeypatch.setenv("RENTIVO_ENCRYPTION_BACKEND", "rot13")
    from rentivo.settings import Settings

    with pytest.raises(ValueError, match="must be one of: base64, kms"):
        Settings(_env_file=None)


def test_encryption_kms_requires_key_id(monkeypatch):
    monkeypatch.setenv("RENTIVO_ENCRYPTION_BACKEND", "kms")
    monkeypatch.delenv("RENTIVO_KMS_KEY_ID", raising=False)
    monkeypatch.setenv("RENTIVO_KMS_REGION", "us-east-1")
    from rentivo.settings import Settings

    with pytest.raises(ValueError, match="RENTIVO_KMS_KEY_ID and RENTIVO_KMS_REGION"):
        Settings(_env_file=None)


def test_encryption_kms_requires_region(monkeypatch):
    monkeypatch.setenv("RENTIVO_ENCRYPTION_BACKEND", "kms")
    monkeypatch.setenv("RENTIVO_KMS_KEY_ID", "alias/rentivo")
    monkeypatch.delenv("RENTIVO_KMS_REGION", raising=False)
    from rentivo.settings import Settings

    with pytest.raises(ValueError, match="RENTIVO_KMS_KEY_ID and RENTIVO_KMS_REGION"):
        Settings(_env_file=None)


def test_encryption_base64_does_not_require_kms_fields(monkeypatch):
    """Default 'base64' backend ignores empty KMS settings."""
    import os

    for key in list(os.environ):
        if key.startswith("RENTIVO_"):
            monkeypatch.delenv(key, raising=False)
    from rentivo.settings import Settings

    s = Settings(_env_file=None)
    assert s.encryption_backend == "base64"
    assert s.kms_key_id == ""


class TestEncryptionCacheSettings:
    def test_cache_backend_defaults_to_none(self):
        s = Settings(_env_file=None)
        assert s.encryption_cache_backend == "none"
        assert s.encryption_cache_ttl_seconds == 60
        assert s.encryption_cache_max_entries == 10_000
        assert s.redis_url == ""

    def test_cache_backend_accepts_memory(self):
        s = Settings(_env_file=None, encryption_cache_backend="memory")
        assert s.encryption_cache_backend == "memory"

    def test_cache_backend_accepts_redis_with_url(self):
        s = Settings(
            _env_file=None,
            encryption_cache_backend="redis",
            redis_url="redis://localhost:6379/0",
        )
        assert s.encryption_cache_backend == "redis"
        assert s.redis_url == "redis://localhost:6379/0"

    def test_cache_backend_rejects_unknown(self):
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=None, encryption_cache_backend="memcached")
        assert "RENTIVO_ENCRYPTION_CACHE_BACKEND" in str(exc.value)

    def test_cache_backend_redis_requires_url(self):
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=None, encryption_cache_backend="redis", redis_url="")
        assert "RENTIVO_REDIS_URL" in str(exc.value)

    def test_cache_ttl_rejects_zero(self):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, encryption_cache_ttl_seconds=0)

    def test_cache_max_entries_rejects_zero(self):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, encryption_cache_max_entries=0)


class TestCacheSettings:
    def test_defaults_to_memory(self):
        s = Settings(_env_file=None)
        assert s.cache_backend == "memory"
        assert s.cache_ttl_seconds == 60
        assert s.cache_max_entries == 2_048

    def test_accepts_none_and_redis_with_url(self):
        assert Settings(_env_file=None, cache_backend="none").cache_backend == "none"
        s = Settings(_env_file=None, cache_backend="redis", redis_url="redis://localhost:6379/0")
        assert s.cache_backend == "redis"

    def test_rejects_unknown_backend(self):
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=None, cache_backend="memcached")
        assert "RENTIVO_CACHE_BACKEND" in str(exc.value)

    def test_redis_requires_url(self):
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=None, cache_backend="redis", redis_url="")
        assert "RENTIVO_CACHE_BACKEND=redis" in str(exc.value)

    def test_ttl_and_max_entries_reject_zero(self):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, cache_ttl_seconds=0)
        with pytest.raises(ValidationError):
            Settings(_env_file=None, cache_max_entries=0)
