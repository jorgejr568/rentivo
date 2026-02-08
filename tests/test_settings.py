from landlord.settings import Settings


class TestSettings:
    def test_defaults(self, monkeypatch):
        # Clear any LANDLORD_ env vars that might interfere
        import os
        for key in list(os.environ):
            if key.startswith("LANDLORD_"):
                monkeypatch.delenv(key, raising=False)
        # Settings reads .env; override by passing values directly
        s = Settings(
            _env_file=None,
            db_backend="sqlite",
            db_path="landlord.db",
        )
        assert s.db_backend == "sqlite"
        assert s.storage_backend == "local"
        assert s.storage_prefix == "bills"
        assert s.s3_presigned_expiry == 604800
        assert s.secret_key == "change-me-in-production"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("LANDLORD_DB_BACKEND", "mysql")
        monkeypatch.setenv("LANDLORD_STORAGE_BACKEND", "s3")
        s = Settings(_env_file=None)
        assert s.db_backend == "mysql"
        assert s.storage_backend == "s3"
