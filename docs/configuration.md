# Configuration Reference

All application settings are environment variables with the `RENTIVO_` prefix, defined in [`rentivo/settings.py`](../rentivo/settings.py) (Pydantic Settings). They can also be placed in a `.env` file at the repo root — copy [`.env.example`](../.env.example) to get started. A test (`tests/test_env_example.py`) keeps `.env.example` in sync with the settings class.

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

## Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_LOG_LEVEL` | `INFO` | structlog level. |
| `RENTIVO_LOG_JSON` | `false` | Emit JSON logs (recommended in production). |

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
| `RENTIVO_SES_CONFIGURATION_SET` | *(empty)* | Optional SES configuration set. |

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
