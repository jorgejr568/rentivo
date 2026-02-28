from rentivo.settings import _INSECURE_DEFAULT_KEY, Settings


class TestSettings:
    def test_defaults(self, monkeypatch):
        # Clear any RENTIVO_ env vars that might interfere
        import os

        for key in list(os.environ):
            if key.startswith("RENTIVO_"):
                monkeypatch.delenv(key, raising=False)
        s = Settings(_env_file=None)
        assert s.db_url == "mysql://rentivo:rentivo@db:3306/rentivo"
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
