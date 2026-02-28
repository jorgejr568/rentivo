import logging
import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_INSECURE_DEFAULT_KEY = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RENTIVO_", extra="ignore")

    db_url: str = "mysql://rentivo:rentivo@db:3306/rentivo"

    storage_backend: str = "local"
    storage_local_path: str = "./invoices"
    storage_prefix: str = "bills"

    s3_bucket: str = ""
    s3_region: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_endpoint_url: str = ""
    s3_presigned_expiry: int = 604800  # 7 days in seconds

    pix_key: str = ""
    pix_merchant_name: str = ""
    pix_merchant_city: str = ""

    log_level: str = "INFO"
    log_json: bool = False

    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "Landlord"
    webauthn_origin: str = "http://localhost:8000"

    secret_key: str = _INSECURE_DEFAULT_KEY

    def get_secret_key(self) -> str:
        if self.secret_key == _INSECURE_DEFAULT_KEY:
            logger.warning(
                "RENTIVO_SECRET_KEY is not set — using a random key. "
                "Sessions will not survive restarts. "
                "Set RENTIVO_SECRET_KEY in your environment or .env file."
            )
            self.secret_key = secrets.token_urlsafe(32)
        return self.secret_key


settings = Settings()
