import re
import secrets

import structlog
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)

_INSECURE_DEFAULT_KEY = "change-me-in-production"
_GTM_RE = re.compile(r"^GTM-[A-Z0-9]+$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RENTIVO_", extra="ignore")

    db_url: str = "mysql+pymysql://rentivo:rentivo@db:3306/rentivo"

    storage_backend: str = "local"
    storage_local_path: str = "./invoices"
    storage_prefix: str = "bills"

    s3_bucket: str = ""
    s3_region: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_endpoint_url: str = ""
    s3_presigned_expiry: int = 604800  # 7 days in seconds

    log_level: str = "INFO"
    log_json: bool = False

    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "Landlord"
    webauthn_origin: str = "http://localhost:8000"

    # Canonical public origin (no trailing slash) used for robots.txt / sitemap.xml / OG tags.
    # Leave empty to derive from the incoming request at runtime.
    public_url: str = ""

    secret_key: str = _INSECURE_DEFAULT_KEY

    gtm_container_id: str = ""
    environment: str = "production"

    @field_validator("gtm_container_id")
    @classmethod
    def _validate_gtm_id(cls, v: str) -> str:
        if v and not _GTM_RE.match(v):
            raise ValueError("RENTIVO_GTM_CONTAINER_ID must match GTM-[A-Z0-9]+ or be empty")
        return v

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, v: str) -> str:
        if v not in ("production", "staging", "dev"):
            raise ValueError("RENTIVO_ENVIRONMENT must be one of: production, staging, dev")
        return v

    email_backend: str = "local"
    email_local_path: str = "./outbox"

    ses_region: str = ""
    ses_access_key_id: str = ""
    ses_secret_access_key: str = ""
    ses_endpoint_url: str = ""
    ses_from_email: str = ""
    ses_configuration_set: str = ""
    public_app_url: str = "http://localhost:8000"

    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""
    turnstile_verify_url: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

    job_worker_batch_size: int = 10
    job_worker_idle_sleep_seconds: float = 5.0
    job_worker_stuck_after_seconds: int = 600

    @field_validator("email_backend")
    @classmethod
    def _validate_email_backend(cls, v: str) -> str:
        if v not in ("local", "ses"):
            raise ValueError("RENTIVO_EMAIL_BACKEND must be one of: local, ses")
        return v

    @model_validator(mode="after")
    def _validate_turnstile_pair(self) -> "Settings":
        site = bool(self.turnstile_site_key)
        secret = bool(self.turnstile_secret_key)
        if site != secret:
            raise ValueError(
                "RENTIVO_TURNSTILE_SITE_KEY and RENTIVO_TURNSTILE_SECRET_KEY must both be set or both empty"
            )
        return self

    def get_secret_key(self) -> str:
        if self.secret_key == _INSECURE_DEFAULT_KEY:
            logger.warning(
                "secret_key_not_configured",
                message=("RENTIVO_SECRET_KEY is not set — using a random key. Sessions will not survive restarts."),
            )
            self.secret_key = secrets.token_urlsafe(32)
        return self.secret_key


settings = Settings()
