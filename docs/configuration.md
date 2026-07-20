# Configuration Reference

All application settings are environment variables with the `RENTIVO_` prefix, defined in [`backend/rentivo/settings.py`](../backend/rentivo/settings.py) (Pydantic Settings). They can also be placed in a `.env` file at the repo root — copy [`.env.example`](../.env.example) to get started. A test (`backend/tests/test_env_example.py`) keeps `.env.example` in sync with the settings class.

Invalid values fail fast at process startup with a clear error.

## Database

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_DB_URL` | `mysql+pymysql://rentivo:rentivo@db:3306/rentivo` | SQLAlchemy URL (MariaDB, PyMySQL driver). Use host `localhost` for processes on your machine; containers started via docker compose are pinned to the `db` service by `docker-compose.yml` and ignore this value. |

The `MYSQL_ROOT_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_PORT` variables in `.env` provision the MariaDB **container** (read by `docker-compose.yml`, not the app).

## Web

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_SECRET_KEY` | `change-me-in-production` | Session signing key. With the default value a random key is generated at boot (sessions reset on restart, a warning is logged). **Rotation caveat:** this key also derives the HMAC key for the `users.email_hash` blind index — after rotating, run `make backfill-encryption-reset-blind-index` or email lookups will silently miss every pre-rotation user. |
| `RENTIVO_PUBLIC_URL` | *(empty)* | Canonical public origin (no trailing slash) for `robots.txt` / `sitemap.xml` / OG tags. Empty = derive from the incoming request. |
| `RENTIVO_PUBLIC_APP_URL` | `http://localhost:8000` | Canonical app URL used inside transactional emails (links, CTAs). |
| `RENTIVO_ENVIRONMENT` | `production` | One of `production` / `staging` / `dev`. Populates the analytics environment dimension. |
| `RENTIVO_ACCESS_COOKIE_NAME` | `__Host-rentivo_access` | Browser login-key cookie. Staging/production require a `__Host-` name. |
| `RENTIVO_CHALLENGE_COOKIE_NAME` | `__Host-rentivo_challenge` | Short-lived authentication challenge cookie. |
| `RENTIVO_CSRF_COOKIE_NAME` | `__Host-rentivo_csrf` | Non-HttpOnly double-submit CSRF cookie. |
| `RENTIVO_COOKIE_SECURE` | `true` | Must remain enabled in staging/production; local HTTP development may disable it. |
| `RENTIVO_API_KEY_LOGIN_TTL_SECONDS` | `86400` | Absolute browser login-key lifetime (24 hours). |
| `RENTIVO_AUTH_CHALLENGE_TTL_SECONDS` | `300` | Authentication challenge lifetime (5 minutes). |
| `RENTIVO_API_KEY_INTEGRATION_DEFAULT_TTL_DAYS` | `90` | Default integration-key lifetime. |
| `RENTIVO_API_KEY_INTEGRATION_MAX_TTL_DAYS` | `365` | Maximum integration-key lifetime. |
| `RENTIVO_API_KEY_LAST_USED_THROTTLE_SECONDS` | `300` | Minimum interval between usage timestamp writes. |

## Observability (OpenTelemetry)

Optional distributed tracing. Disabled by default; see [`docs/observability.md`](observability.md) for the full guide.

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_OTEL_ENABLED` | `false` | Master switch. When `false` (or the `otel` extra is not installed) no spans are produced and no network calls are made. |
| `RENTIVO_OTEL_SERVICE_NAME` | `rentivo` | `service.name` resource attribute shown in the trace UI. |
| `RENTIVO_OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | OTLP/HTTP base URL (used when `RENTIVO_OTEL_EXPORTER=otlp`); the SDK appends `/v1/traces`. Use `http://jaeger:4318` on the compose network. |
| `RENTIVO_OTEL_SAMPLE_RATIO` | `1.0` | Head sampling ratio (0.0–1.0), parent-based. |
| `RENTIVO_OTEL_EXPORTER` | `otlp` | `otlp` (generic collector/Jaeger) or `cloudwatch` (AWS X-Ray / CloudWatch Transaction Search OTLP endpoint, SigV4-signed). |
| `RENTIVO_OTEL_AWS_REGION` | *(empty)* | Required when `RENTIVO_OTEL_EXPORTER=cloudwatch`. Endpoint is `https://xray.<region>.amazonaws.com/v1/traces`. |
| `RENTIVO_OTEL_AWS_ACCESS_KEY_ID` | *(empty)* | Optional creds for the cloudwatch exporter; empty = standard AWS credential chain. |
| `RENTIVO_OTEL_AWS_SECRET_ACCESS_KEY` | *(empty)* | Optional secret for the cloudwatch exporter. |

## Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_LOG_LEVEL` | `INFO` | structlog level. |
| `RENTIVO_LOG_JSON` | `false` | Emit JSON logs (recommended in production). |
| `RENTIVO_LOG_CLOUDWATCH_ENABLED` | `false` | Ship a JSON copy of logs to CloudWatch Logs via watchtower (stdout is unaffected). When tracing is on, each log also carries `trace_id`/`span_id`. |
| `RENTIVO_LOG_CLOUDWATCH_GROUP` | `rentivo` | Target CloudWatch log group. |
| `RENTIVO_LOG_CLOUDWATCH_STREAM` | *(empty)* | Log stream name; empty = watchtower default `{machine_name}/{program_name}`. |
| `RENTIVO_LOG_CLOUDWATCH_REGION` | *(empty)* | Required when `RENTIVO_LOG_CLOUDWATCH_ENABLED=true`. |
| `RENTIVO_LOG_CLOUDWATCH_ACCESS_KEY_ID` | *(empty)* | Optional; empty = standard AWS credential chain. |
| `RENTIVO_LOG_CLOUDWATCH_SECRET_ACCESS_KEY` | *(empty)* | Optional secret for the above. |

## WebAuthn / Passkeys

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_WEBAUTHN_RP_ID` | `localhost` | Relying-party ID. Must match the domain users visit; changing it invalidates registered passkeys. |
| `RENTIVO_WEBAUTHN_RP_NAME` | `Rentivo` | Display name shown in browser passkey prompts. |
| `RENTIVO_WEBAUTHN_ORIGIN` | `http://localhost:8000` | Expected origin for WebAuthn ceremonies. |

## Storage (invoice PDFs)

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_STORAGE_BACKEND` | `local` | `local` or `s3`. |
| `RENTIVO_STORAGE_LOCAL_PATH` | `./invoices` | Directory for the local backend. |
| `RENTIVO_STORAGE_PREFIX` | `bills` | Key prefix prepended to stored objects. |
| `RENTIVO_S3_BUCKET` | *(empty)* | S3 bucket (s3 backend only). |
| `RENTIVO_S3_REGION` | *(empty)* | AWS region. |
| `RENTIVO_S3_ACCESS_KEY_ID` | *(empty)* | AWS access key. |
| `RENTIVO_S3_SECRET_ACCESS_KEY` | *(empty)* | AWS secret key. |
| `RENTIVO_S3_ENDPOINT_URL` | *(empty)* | Custom endpoint (MinIO, LocalStack). |
| `RENTIVO_S3_PRESIGNED_EXPIRY` | `604800` | Presigned URL expiry in seconds (7 days). |

## Email

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_EMAIL_BACKEND` | `local` | `local` or `ses`. The local backend writes `.eml` files instead of calling AWS. |
| `RENTIVO_EMAIL_LOCAL_PATH` | `./outbox` | Output directory for the local backend. |
| `RENTIVO_SES_REGION` | *(empty)* | AWS SES region (ses backend only). |
| `RENTIVO_SES_ACCESS_KEY_ID` | *(empty)* | AWS access key. |
| `RENTIVO_SES_SECRET_ACCESS_KEY` | *(empty)* | AWS secret key. |
| `RENTIVO_SES_ENDPOINT_URL` | *(empty)* | Custom endpoint (LocalStack). |
| `RENTIVO_SES_FROM_EMAIL` | *(empty)* | From address (must be SES-verified). |
| `RENTIVO_SES_FROM_NAME` | *(empty)* | Optional display name for account/security/transactional email From, rendered as `Name <email>`; empty sends a bare address. |
| `RENTIVO_SES_CONFIGURATION_SET` | *(empty)* | Optional SES configuration set. |
| `RENTIVO_COMMUNICATIONS_FROM_EMAIL` | *(empty)* | From address used only for tenant communication emails; empty falls back to `RENTIVO_SES_FROM_EMAIL`; account/security emails unaffected. |
| `RENTIVO_COMMUNICATIONS_FROM_NAME` | *(empty)* | Display name for tenant communication email From only; empty falls back to `RENTIVO_SES_FROM_NAME`. |

## Field encryption (PII at rest)

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_ENCRYPTION_BACKEND` | `base64` | `base64` or `kms`. **base64 is reversible obfuscation, NOT encryption** — use `kms` in production. After switching, run `make backfill-encryption` (preview with `make backfill-encryption-dry`). |
| `RENTIVO_KMS_KEY_ID` | *(empty)* | KMS key id or alias. Required (with region) when backend is `kms`. **Enable deletion protection** — losing the key loses all encrypted PII permanently. |
| `RENTIVO_KMS_REGION` | *(empty)* | AWS region. Required when backend is `kms`. |
| `RENTIVO_KMS_ACCESS_KEY_ID` | *(empty)* | AWS access key. |
| `RENTIVO_KMS_SECRET_ACCESS_KEY` | *(empty)* | AWS secret key. |
| `RENTIVO_KMS_ENDPOINT_URL` | *(empty)* | Custom endpoint (LocalStack KMS). |

## Decryption cache

Caches `decrypt()` results in front of the encryption backend to cut KMS round-trips. Independent from the generic cache below.

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_ENCRYPTION_CACHE_BACKEND` | `none` | `none` / `memory` / `redis`. |
| `RENTIVO_ENCRYPTION_CACHE_TTL_SECONDS` | `60` | Entry TTL (>= 1). |
| `RENTIVO_ENCRYPTION_CACHE_MAX_ENTRIES` | `10000` | Bound for the memory backend (>= 1). |

## Generic application cache

Used for KPI rollups on the billing list, and future consumers.

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_CACHE_BACKEND` | `memory` | `none` / `memory` / `redis`. |
| `RENTIVO_CACHE_TTL_SECONDS` | `60` | Entry TTL (>= 1). |
| `RENTIVO_CACHE_MAX_ENTRIES` | `2048` | Bound for the memory backend (>= 1). |

## Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_REDIS_URL` | *(empty)* | Shared by both caches. Required iff either cache backend is `redis`. Run Redis on a private network with auth; prefer `rediss://`. The `redis` Python package is an extra: `uv sync --extra cache`. |

## Bot protection (Cloudflare Turnstile)

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_TURNSTILE_SITE_KEY` | *(empty)* | Set **both** keys to enable, leave **both** empty to disable (validated at boot). Gates `/login`, `/signup`, `/forgot-password`. |
| `RENTIVO_TURNSTILE_SECRET_KEY` | *(empty)* | Server-side verification key. |
| `RENTIVO_TURNSTILE_VERIFY_URL` | Cloudflare public URL | Override for self-hosted gateways. |

## Analytics (Google Tag Manager)

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_GTM_CONTAINER_ID` | *(empty)* | `GTM-XXXXXXX` enables analytics; empty fully disables it (no scripts, no cookies). Must match `GTM-[A-Z0-9]+`. |

## Background job worker

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_JOB_WORKER_BATCH_SIZE` | `10` | Jobs claimed per polling cycle. |
| `RENTIVO_JOB_WORKER_IDLE_SLEEP_SECONDS` | `5.0` | Sleep between polls when the queue is empty. |
| `RENTIVO_JOB_WORKER_STUCK_AFTER_SECONDS` | `600` | Jobs claimed longer than this are considered stuck and re-queued. |
| `RENTIVO_JOB_BACKEND` | `database` | Job driver: `database` (built-in polling worker, no extra deps) or `temporal`. |
| `RENTIVO_TEMPORAL_HOST` | `localhost:7233` | Temporal frontend host:port. Only used when `RENTIVO_JOB_BACKEND=temporal`. |
| `RENTIVO_TEMPORAL_NAMESPACE` | `default` | Temporal namespace. |
| `RENTIVO_TEMPORAL_TASK_QUEUE` | `rentivo-jobs` | Task queue shared by enqueuers and workers. |
| `RENTIVO_TEMPORAL_TLS` | `false` | Connect to Temporal over TLS (e.g. Temporal Cloud). |
| `RENTIVO_TEMPORAL_ACTIVITY_START_TO_CLOSE_TIMEOUT_SECONDS` | `600` | Per-attempt activity timeout. |

Temporal is an optional driver — the `database` driver is fully supported in production and requires no additional services. See `docs/jobs.md`.
