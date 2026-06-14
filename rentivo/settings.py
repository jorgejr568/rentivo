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
    webauthn_rp_name: str = "Rentivo"
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
    # Optional display name for the From of account/security/transactional emails
    # (rendered as "Name <email>"); empty sends a bare address.
    ses_from_name: str = ""
    ses_configuration_set: str = ""
    # Optional override for the From address of tenant communication emails only.
    # Empty falls back to ses_from_email (then "noreply@localhost"). Account /
    # security / transactional emails always use ses_from_email.
    communications_from_email: str = ""
    # Optional display name for communication emails only; empty falls back to ses_from_name.
    communications_from_name: str = ""
    public_app_url: str = "http://localhost:8000"

    encryption_backend: str = "base64"
    kms_key_id: str = ""
    kms_region: str = ""
    kms_access_key_id: str = ""
    kms_secret_access_key: str = ""
    kms_endpoint_url: str = ""

    encryption_cache_backend: str = "none"
    encryption_cache_ttl_seconds: int = 60
    encryption_cache_max_entries: int = 10_000
    redis_url: str = ""

    cache_backend: str = "memory"
    cache_ttl_seconds: int = 60
    cache_max_entries: int = 2_048

    # OpenTelemetry tracing. Fully optional: off unless RENTIVO_OTEL_ENABLED=true
    # AND the `otel` extra is installed. No collector dependency is forced.
    otel_enabled: bool = False
    otel_service_name: str = "rentivo"
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_sample_ratio: float = 1.0
    # Exporter: `otlp` (generic OTLP/HTTP, e.g. Jaeger) or `cloudwatch`
    # (AWS X-Ray / CloudWatch Transaction Search OTLP endpoint, SigV4-signed).
    otel_exporter: str = "otlp"
    otel_aws_region: str = ""
    # Optional explicit creds for the cloudwatch exporter; empty falls back to
    # the standard AWS credential chain (env / instance-profile / task role).
    otel_aws_access_key_id: str = ""
    otel_aws_secret_access_key: str = ""

    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""
    turnstile_verify_url: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

    google_auth_enabled: bool = False
    google_client_id: str = ""
    google_client_secret: str = ""

    # Banco Central SGS API base URL (override for tests/LocalStack). The
    # readjustment flow appends /dados/serie/bcdata.sgs.{code}/dados/ultimos/12.
    bcb_sgs_base_url: str = "https://api.bcb.gov.br"

    job_worker_batch_size: int = 10
    job_worker_idle_sleep_seconds: float = 5.0
    job_worker_stuck_after_seconds: int = 600

    # Background-job execution driver. `database` (default) uses the built-in
    # polling worker over the `jobs` table — zero extra dependencies. `temporal`
    # offloads execution to a Temporal cluster (requires the `temporal` extra;
    # NOT required for production — the database driver is fully supported).
    job_backend: str = "database"

    # Temporal connection (only used when RENTIVO_JOB_BACKEND=temporal).
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "rentivo-jobs"
    temporal_tls: bool = False
    temporal_activity_start_to_close_timeout_seconds: int = 600

    # Ship logs to CloudWatch Logs (additive — stdout is unaffected). Off by
    # default; uses the standard AWS credential chain unless explicit creds set.
    log_cloudwatch_enabled: bool = False
    log_cloudwatch_group: str = "rentivo"
    log_cloudwatch_stream: str = ""  # empty → watchtower default ("{machine_name}/{program_name}")
    log_cloudwatch_region: str = ""
    log_cloudwatch_access_key_id: str = ""
    log_cloudwatch_secret_access_key: str = ""

    @field_validator("email_backend")
    @classmethod
    def _validate_email_backend(cls, v: str) -> str:
        if v not in ("local", "ses"):
            raise ValueError("RENTIVO_EMAIL_BACKEND must be one of: local, ses")
        return v

    @field_validator("encryption_backend")
    @classmethod
    def _validate_encryption_backend(cls, v: str) -> str:
        if v not in ("base64", "kms"):
            raise ValueError("RENTIVO_ENCRYPTION_BACKEND must be one of: base64, kms")
        return v

    @field_validator("encryption_cache_backend")
    @classmethod
    def _validate_encryption_cache_backend(cls, v: str) -> str:
        if v not in ("none", "memory", "redis"):
            raise ValueError("RENTIVO_ENCRYPTION_CACHE_BACKEND must be one of: none, memory, redis")
        return v

    @field_validator("encryption_cache_ttl_seconds")
    @classmethod
    def _validate_encryption_cache_ttl(cls, v: int) -> int:
        if v < 1:
            raise ValueError("RENTIVO_ENCRYPTION_CACHE_TTL_SECONDS must be >= 1")
        return v

    @field_validator("encryption_cache_max_entries")
    @classmethod
    def _validate_encryption_cache_max_entries(cls, v: int) -> int:
        if v < 1:
            raise ValueError("RENTIVO_ENCRYPTION_CACHE_MAX_ENTRIES must be >= 1")
        return v

    @field_validator("cache_backend")
    @classmethod
    def _validate_cache_backend(cls, v: str) -> str:
        if v not in ("none", "memory", "redis"):
            raise ValueError("RENTIVO_CACHE_BACKEND must be one of: none, memory, redis")
        return v

    @field_validator("job_backend")
    @classmethod
    def _validate_job_backend(cls, v: str) -> str:
        if v not in ("database", "temporal"):
            raise ValueError("RENTIVO_JOB_BACKEND must be one of: database, temporal")
        return v

    @field_validator("cache_ttl_seconds")
    @classmethod
    def _validate_cache_ttl(cls, v: int) -> int:
        if v < 1:
            raise ValueError("RENTIVO_CACHE_TTL_SECONDS must be >= 1")
        return v

    @field_validator("cache_max_entries")
    @classmethod
    def _validate_cache_max_entries(cls, v: int) -> int:
        if v < 1:
            raise ValueError("RENTIVO_CACHE_MAX_ENTRIES must be >= 1")
        return v

    @field_validator("otel_sample_ratio")
    @classmethod
    def _validate_otel_sample_ratio(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("RENTIVO_OTEL_SAMPLE_RATIO must be between 0.0 and 1.0")
        return v

    @field_validator("otel_exporter")
    @classmethod
    def _validate_otel_exporter(cls, v: str) -> str:
        if v not in ("otlp", "cloudwatch"):
            raise ValueError("RENTIVO_OTEL_EXPORTER must be one of: otlp, cloudwatch")
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

    @model_validator(mode="after")
    def _validate_google_auth(self) -> "Settings":
        if self.google_auth_enabled and (not self.google_client_id or not self.google_client_secret):
            raise ValueError(
                "RENTIVO_GOOGLE_CLIENT_ID and RENTIVO_GOOGLE_CLIENT_SECRET are required "
                "when RENTIVO_GOOGLE_AUTH_ENABLED=true"
            )
        return self

    @model_validator(mode="after")
    def _validate_kms_pair(self) -> "Settings":
        if self.encryption_backend == "kms" and (not self.kms_key_id or not self.kms_region):
            raise ValueError(
                "RENTIVO_KMS_KEY_ID and RENTIVO_KMS_REGION are required when RENTIVO_ENCRYPTION_BACKEND=kms"
            )
        return self

    @model_validator(mode="after")
    def _validate_temporal(self) -> "Settings":
        if self.job_backend == "temporal":
            if not self.temporal_host:
                raise ValueError("RENTIVO_TEMPORAL_HOST is required when RENTIVO_JOB_BACKEND=temporal")
            if not self.temporal_namespace:
                raise ValueError("RENTIVO_TEMPORAL_NAMESPACE is required when RENTIVO_JOB_BACKEND=temporal")
            if not self.temporal_task_queue:
                raise ValueError("RENTIVO_TEMPORAL_TASK_QUEUE is required when RENTIVO_JOB_BACKEND=temporal")
        return self

    @model_validator(mode="after")
    def _validate_redis_url_required(self) -> "Settings":
        if self.encryption_cache_backend == "redis" and not self.redis_url:
            raise ValueError("RENTIVO_REDIS_URL is required when RENTIVO_ENCRYPTION_CACHE_BACKEND=redis")
        if self.cache_backend == "redis" and not self.redis_url:
            raise ValueError("RENTIVO_REDIS_URL is required when RENTIVO_CACHE_BACKEND=redis")
        return self

    @model_validator(mode="after")
    def _validate_otel_cloudwatch(self) -> "Settings":
        if self.otel_enabled and self.otel_exporter == "cloudwatch" and not self.otel_aws_region:
            raise ValueError("RENTIVO_OTEL_AWS_REGION is required when RENTIVO_OTEL_EXPORTER=cloudwatch")
        return self

    @model_validator(mode="after")
    def _validate_log_cloudwatch(self) -> "Settings":
        if self.log_cloudwatch_enabled and not self.log_cloudwatch_region:
            raise ValueError("RENTIVO_LOG_CLOUDWATCH_REGION is required when RENTIVO_LOG_CLOUDWATCH_ENABLED=true")
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
