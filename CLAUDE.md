# Rentivo

Apartment billing management with PDF invoice generation — CLI + FastAPI web UI.

## Running

```bash
# Start MariaDB (required)
docker compose up -d db

# CLI (local)
make run

# Web (local)
make migrate             # first time only
make web-createuser      # first time only
make web-run             # http://localhost:8000
```

## Scripts

```bash
# Local
make regenerate-pdfs
make regenerate-pdfs-dry

# Docker
make docker-regenerate
```

## Docker

Two Dockerfiles:
- **`Dockerfile`** — Web app (FastAPI + uvicorn on port 8000)
- **`Dockerfile.cli`** — CLI container (health check on port 2019)

```bash
# Web container (default)
make build       # build web image
make up          # start web container (port 8000)
make down        # stop and remove
make restart     # down + up
make logs        # tail logs
make health      # curl http://localhost:8000

# CLI container
make build-cli   # build CLI image
make up-cli      # start CLI container (port 2019)
make down-cli    # stop and remove
make rentivo    # run CLI interactively
make shell-cli   # bash session

# Docker Compose (both services)
make compose-up            # start web + cli
make compose-down          # stop all
make compose-rentivo      # run CLI in cli container
make compose-createuser    # create web user
```

## Architecture

- **Settings**: `rentivo/settings.py` — Pydantic Settings, env prefix `RENTIVO_`, reads `.env`
- **Database**: `rentivo/db.py` — SQLAlchemy engine + connection to MariaDB. Schema managed by Alembic. Configured via `RENTIVO_DB_URL`
- **Repositories**: `rentivo/repositories/` — Abstract base classes in `base.py`, SQLAlchemy Core impl in `sqlalchemy.py`, factory in `factory.py`
- **Storage**: `rentivo/storage/` — Same pattern. `LocalStorage` writes to `./invoices/`, `S3Storage` uploads to a private bucket with presigned URLs. Configurable via `RENTIVO_STORAGE_BACKEND`
- **PDF**: `rentivo/pdf/invoice.py` — fpdf2-based invoice with navy/green color palette; `rentivo/pdf/merger.py` — merges receipt attachments into invoices using pypdf
- **Services**: `rentivo/services/` — Business logic layer wiring repos + storage + PDF
- **CLI**: `rentivo/cli/` — Interactive menus using `questionary` + `rich`
- **Health check**: `healthcheck.py` — HTTP server on port 2019, returns 200 for all requests

## S3 Storage

- Invoice S3 key pattern: `{billing_uuid}/{bill_uuid}.pdf`
- Receipt S3 key pattern: `{billing_uuid}/{bill_uuid}/receipts/{receipt_uuid}{ext}`
- `pdf_path` column stores the S3 key, not a URL
- Presigned URLs (7-day expiry) are generated on the fly via `get_invoice_url()` / `get_presigned_url()`
- Set `RENTIVO_STORAGE_BACKEND=s3` and configure `RENTIVO_S3_*` env vars

## Conventions

- All customer-facing text (CLI prompts, PDF content) in **PT-BR**
- Currency in **BRL** (R$), formatted via `rentivo.models.format_brl()`
- Money stored as **centavos (int)** in the database — never use floats for money
- Code (variable names, comments) in English

## FastAPI Web App

The `web/` directory contains a FastAPI web application that provides a browser-based UI for the same functionality as the CLI.

### Running

```bash
make migrate             # run Alembic migrations (creates users table etc.)
make web-createuser      # create web login user
make web-run             # start uvicorn at http://localhost:8000
```

### Architecture

- **App**: `web/app.py` — FastAPI app, SessionMiddleware, Jinja2 templates, static files
- **Auth**: `web/auth.py` — login/logout routes, session-based auth
- **Middleware**: `web/deps.py` — AuthMiddleware (redirects to /login), service factories, render helper
- **Flash**: `web/flash.py` — session-based flash messages
- **Forms**: `web/forms.py` — `parse_brl()` and `parse_formset()` helpers
- **Routes**: `web/routes/billing.py`, `web/routes/bill.py` (includes receipt upload/delete)
- **Templates**: Jinja2 with Bootstrap 5 via CDN, all customer-facing text in PT-BR
- **Static**: `web/static/core/` — CSS and JS (served via Starlette StaticFiles)

### Key URLs

| URL | Purpose |
|-----|---------|
| `/` | Redirect to billing list |
| `/billings/` | Billing list |
| `/billings/create` | Create new billing |
| `/billings/<id>` | Billing detail + bills |
| `/billings/<id>/edit` | Edit billing |
| `/billings/<id>/bills/generate` | Generate new bill |
| `/billings/<id>/bills/<bill_id>` | Bill detail |
| `/billings/<id>/bills/<bill_id>/edit` | Edit bill |
| `/billings/<id>/bills/<bill_id>/invoice` | Download/view PDF |
| `POST /billings/<id>/bills/<bill_id>/receipts/upload` | Upload receipt attachment |
| `POST /billings/<id>/bills/<bill_id>/receipts/<receipt_id>/delete` | Delete receipt attachment |
| `/login` | Login page |
| `/logout` | Logout |
| `/change-password` | Change password |

## Receipt Attachments

- Bills can have attached receipt files (PDF, JPEG, PNG, max 10 MB)
- Receipt storage key pattern: `{billing_uuid}/{bill_uuid}/receipts/{receipt_uuid}{ext}`
- Receipts are merged into the generated PDF invoice using pypdf (appended after invoice pages, in order of addition)
- Model: `rentivo/models/receipt.py`, Repository: `ReceiptRepository`, Service: integrated into `BillService`
- Upload/delete via separate forms on the bill edit page

## Audit Logging

- **AuditService** logs all state-changing operations across web and CLI
- Event types defined in `rentivo/models/audit_log.py` (`AuditEventType`)
- Serializers in `rentivo/services/audit_serializers.py` strip sensitive fields (`password_hash`) and partial-mask redact PII via `rentivo/pii_redaction.py:redact()`. PIX fields (`pix_key`, `pix_merchant_name`, `pix_merchant_city`) and `to_email` in `email.send` job payloads are stored under their original field names with masked values: PIX fields show first 3 chars + `...` + last 2 (e.g. `123...01`); emails show first 2 chars of local + `...@` + full domain (e.g. `jo...@gmail.com`). Short values collapse to `***`. The mask is one-way, key-less, and deterministic — no `secret_key` dependency, no per-environment correlation key. Reviewers can recognize "same value across rows" via equal masked strings without seeing the plaintext.
- Backfill: `make redact-audit-logs-dry` previews; `make redact-audit-logs` rewrites legacy `audit_logs` rows whose JSON still contains plaintext PII. Idempotent (the redaction function is its own fixed point on typical inputs). Run once after deploying the redacted serializers.
- `safe_log()` swallows exceptions — audit failures never block business operations
- Web routes: actor context comes from session (`user_id`, `username`)
- CLI: uses `source="cli"`, `actor_id=None`, `actor_username=""`
- States stored as JSON TEXT in `previous_state` / `new_state` columns

## Analytics (Google Tag Manager)

Rentivo integrates with Google Tag Manager gated by a single env var.

### Configuration

- `RENTIVO_GTM_CONTAINER_ID` — e.g. `GTM-ABC1234`. Empty string fully disables analytics (no script tags, no network calls, no cookies, no tests affected). Validator enforces `GTM-[A-Z0-9]+`.
- `RENTIVO_ENVIRONMENT` — `production` (default) | `staging` | `dev`. Populates the `environment` dataLayer field so GA4 can filter environments.

### How it works

- `web/analytics.py` owns the server-side helpers: `analytics_hash()` (HMAC-SHA256 of identifiers, keyed by `secret_key`), `build_page_context()` (initial dataLayer push), `push_event()` / `pop_events()` (flash-style queue for post-redirect business events).
- `web/deps.py:render()` injects `gtm_initial_push` and drains `gtm_pending_events` on every rendered page.
- `web/templates/base.html` renders the GTM loader + noscript iframe + inline `dataLayer.push(...)` calls only when `gtm_container_id` is set.
- `web/static/core/js/tracking.js` installs automatic listeners for forms, clicks, uploads, performance, errors, and engagement. No-ops without `window.dataLayer`.
- `web/static/core/vendor/web-vitals.iife.js` is vendored from `web-vitals@4.2.4` and reports Core Web Vitals.

### Event taxonomy

- **Page context** — `page_context` initial push on every page with `user_status`, `user_id_hash`, `page_type`, `page_template`, `environment`, `app_version`, `request_id`.
- **Using** — `form_start`, `form_submit`, `button_click`, `link_click`, `download_click`, `file_upload_*`, `scroll_depth`, `page_engaged`, `time_on_page`, and business events (`rentivo_*`).
- **Suffering** — `form_submit_error`, `form_field_error`, `form_abandon`, `rage_click`, `js_error`, `promise_rejection`.
- **Issues** — `network_error`, `file_upload_error`.
- **Waiting** — `web_vital` (LCP/INP/CLS/TTFB/FCP), `slow_page`, `interaction_slow`, `layout_shift_bad`, `long_task`, `slow_form_submit`.
- **Business** — `rentivo_bill_generated`, `rentivo_billing_created/edited/deleted/transferred`, `rentivo_bill_*`, `rentivo_invoice_downloaded`, `rentivo_receipt_uploaded/deleted`, `rentivo_login_success/failed`, `rentivo_logout`, `rentivo_signup_completed`, `rentivo_password_changed`, `rentivo_mfa_*`, `rentivo_passkey_*`, `rentivo_organization_created`, `rentivo_invite_*`, `rentivo_theme_changed`.

### Privacy

- **Never** push to dataLayer: `username`, `email`, `pix_key`, `pix_merchant_name`, `pix_merchant_city`, bill item descriptions, receipt filenames, organization names, or raw UUIDs. All identifiers must go through `analytics_hash()`.
- URL paths are sanitized by `tracking.js` (`/:uuid`, `/:ulid`, `/:id`) before being included in `network_error` events.
- LGPD: legitimate interest (art. 7 IX) for authenticated B2B product analytics. No cookie banner required for launch. User opt-out toggle and `/privacy` policy page are deferred follow-ups.

### Testing

- `tests/web/test_analytics.py` — unit tests for hashing, page context, event queue.
- `tests/web/test_gtm_integration.py` — integration tests for template rendering (disabled and enabled modes).
- `tests/web/test_gtm_events.py` — integration tests verifying business events fire on successful state-changing POSTs.
- Tests use `TestClient` (no JS execution), so there is no risk of hitting `googletagmanager.com` during tests.

## Alembic Migrations

- **NEVER invent revision IDs manually** — always generate them with `alembic.util.rev_id()` or by running `alembic revision -m "description"` and using the generated file
- Revision IDs must be proper hex strings (e.g. `268d02b96390`), not made-up patterns like `g1h2i3j4k5l6`
- Migration file naming: `{revision_id}_{slug}.py` (e.g. `268d02b96390_add_mfa_tables.py`)

## Pull Requests

When the user asks you to open a PR, you are responsible for filling out the PR template at `.github/pull_request_template.md`. Fetch the template with `gh api repos/:owner/:repo/contents/.github/pull_request_template.md --jq '.content' | base64 -d` if you need to refresh your memory of its structure — or reuse the structure below.

**Required sections (all must be addressed; delete only sections explicitly marked "delete if N/A"):**

1. **Summary** — 1-3 bullets. Lead with the *why* (the user-visible motivation), not the *what*.
2. **What changed** — concrete, scannable list of modifications by file/component.
3. **Test plan** — checklist covering:
   - `pytest -n auto` passed
   - `ruff check .` and `ruff format --check .` clean
   - Manual smoke (describe the flow, or write "N/A")
   - Any feature-specific verification steps the reviewer should run
4. **Screenshots / recordings** — include before/after for UI changes; delete section if no UI.
5. **Config / deployment notes** — env vars added, migrations required, feature flags, rollout order. Write "None" if nothing.
6. **Risk & rollback** — one line on blast radius, one line on how to revert.
7. **Related** — linked issues, specs, prior PRs; delete if N/A.

**Tone:** Terse, factual, in English. Assume the reviewer is a teammate who has not read the implementation.

**Use HEREDOC when creating the PR** to preserve newlines — see the `gh pr create` pattern in the main instructions.

## Email (SES)

- Backend selected via `RENTIVO_EMAIL_BACKEND` (`local` | `ses`).
- Local backend writes `.eml` files to `RENTIVO_EMAIL_LOCAL_PATH` (default `./outbox`) so dev runs never call AWS.
- SES backend uses `RENTIVO_SES_*` env vars (mirror of S3 credentials). Optional `RENTIVO_SES_ENDPOINT_URL` for LocalStack and `RENTIVO_SES_CONFIGURATION_SET` for SES configuration sets.
- Templates live in `web/templates/emails/*.html` + `*.txt`. PT-BR copy.
- `EmailService.send_password_recovery(to_email, reset_url)` is the only consumer for now.

## Password Recovery

- Routes: `/forgot-password`, `/reset-password` (both public).
- Tokens are stored hashed (SHA-256) in `password_reset_tokens`; only the raw token (URL-safe, 48 bytes) is emailed.
- TTL: 1 hour. Single-use. On consumption all other unused tokens for the user are invalidated.
- "Unknown email" returns the same UI as "email sent" — no enumeration.
- Audit events: `user.password_reset_requested`, `user.password_reset_completed`.

## Transactional Emails

### Account & security emails

All dispatched via `EmailService.safe_send_*` (swallow failures, never block the auth flow):

- `welcome` — on signup. Links to PIX setup (`/security/pix`).
- `password_changed` — fires from `/security/change-password` and from successful `/reset-password`. Body shows time + `request.client.host` + a "redefinir senha" CTA pointing at `/forgot-password`.
- `mfa_changed` — fires from TOTP enable/disable and passkey register/delete in `web/routes/security.py`. Distinct `change_label` per kind (TOTP ativado / desativado, Passkey registrado / removido).
- `new_device_login` — fires on the first login from an unseen `(user_agent, IPv4 /24)` pair. Backed by `known_devices` (Alembic `9a1c5b3f7e62`) and `KnownDeviceService.fingerprint(user_agent, remote_ip)` which SHA-256s `"<UA>|<subnet>"`.

### Organization & collaboration emails

- `invite_received` — to the invitee when an org admin sends an invite (`web/routes/organization.py`). Links to `/invites/`.
- `invite_responded` — to the original inviter when the invitee accepts or declines (`web/routes/invite.py`). `response_label` is `"aceitou"` or `"recusou"`.
- `member_changed` — to the affected user when their role changes in an org (`web/routes/organization.py:member_change_role`).
- `billing_transferred` — fires from `web/routes/billing.py` transfer handler. Notifies the previous user-owner (if any) and every `admin`/`owner` member of the destination organization.

## Field Encryption (KMS)

Selected PII columns are encrypted at rest behind a pluggable backend abstraction.

### Encrypted columns

| Table | Columns |
|-------|---------|
| `users` | `email`, `pix_key`, `pix_merchant_name`, `pix_merchant_city` |
| `organizations` | `pix_key`, `pix_merchant_name`, `pix_merchant_city` |
| `billings` | `pix_key`, `pix_merchant_name`, `pix_merchant_city`, `name`, `description` |
| `billing_items` | `description` |
| `bills` | `notes` |
| `bill_line_items` | `description` |
| `receipts` | `filename` |
| `user_totp` | `secret` |

Other sensitive values (`password_hash`, `*_token_hash`, `*_code_hash`, `device_hash`) are already one-way hashes; passkey columns are public-by-design WebAuthn material; `user_passkeys.credential_id` is looked up by value (`WHERE = ?`) and requires a deterministic-cipher + blind-index design tracked under future work. See `docs/superpowers/plans/2026-05-03-kms-encryption.md`, `docs/superpowers/plans/2026-05-04-extend-kms-encryption.md`, and `docs/superpowers/plans/2026-05-12-encrypt-user-email.md` for the full rationale.

### Configuration

- `RENTIVO_ENCRYPTION_BACKEND` — `base64` (default — local-only obfuscation, NOT encryption) or `kms`.
- `RENTIVO_KMS_KEY_ID` — the KMS key id or alias (e.g. `alias/rentivo`).
- `RENTIVO_KMS_REGION`, `RENTIVO_KMS_ACCESS_KEY_ID`, `RENTIVO_KMS_SECRET_ACCESS_KEY` — AWS credentials.
- `RENTIVO_KMS_ENDPOINT_URL` — optional override for LocalStack KMS.

When `RENTIVO_ENCRYPTION_BACKEND=kms`, both `RENTIVO_KMS_KEY_ID` and `RENTIVO_KMS_REGION` are required (Settings validator enforces this at startup).

### Blind index for `users.email`

Because KMS ciphertext is non-deterministic, `WHERE email = ?` no longer works. A second column `users.email_hash` (`CHAR(64)`, `UNIQUE`) stores `HMAC-SHA256(normalize(email), K)` where `normalize` is `.strip().lower()`. The repository computes the hash on writes and matches on `email_hash` on reads (`SQLAlchemyUserRepository.get_by_email`).

The HMAC key `K` derives from `RENTIVO_SECRET_KEY` (the existing session secret) via `SHA-256` over a fixed domain-prefix. No additional env var or KMS setup is required. The trade-off is explicit: anyone with read access to the env var can recompute the index and probe "is email X a user?" against the DB, though `email` itself stays KMS-encrypted at rest.

The Alembic migration that adds `email_hash` also runs `UPDATE users SET email = LOWER(TRIM(email))` so legacy plaintext rows match the same normalization the hash applies. Any pre-existing case-variant duplicates (e.g. `Alice@x.com` and `alice@x.com` as separate accounts) survive the migration and are caught by the new `UNIQUE(email_hash)` at backfill time — surfaced loudly, not silently merged.

Rotating `RENTIVO_SECRET_KEY` invalidates every existing `users.email_hash`. After rotation, run `make backfill-encryption-reset-blind-index` — which NULLs every hash and re-populates it under the new key. A plain `make backfill-encryption` would skip the stale rows and leave the entire user table indexed under the previous key. Note that session-secret rotation also invalidates active sessions; plan both in the same window.

### Architecture

- `rentivo/encryption/base.py:EncryptionBackend` — abstract `encrypt` / `decrypt` / `is_encrypted` interface. All three are idempotent: `encrypt` is a no-op on already-encrypted values, `decrypt` is a no-op on plaintext (or any value not produced by this backend).
- `rentivo/encryption/base64.py:Base64Backend` — local-only obfuscation. NOT encryption. Ciphertext format: `b64:v1:<base64(plaintext)>`.
- `rentivo/encryption/kms.py:KMSBackend` — calls `kms.Encrypt` / `kms.Decrypt` directly (no envelope DEK). Ciphertext format: `enc:v1:<base64-of-CiphertextBlob>`.
- `rentivo/encryption/factory.py:get_encryption` — dispatches by `RENTIVO_ENCRYPTION_BACKEND`.
- Wired into `SQLAlchemyBillingRepository`, `SQLAlchemyBillRepository`, `SQLAlchemyReceiptRepository`, `SQLAlchemyUserRepository`, `SQLAlchemyOrganizationRepository`, `SQLAlchemyMFATOTPRepository`, `SQLAlchemyInviteRepository`. Encryption happens on writes; decryption on reads.
- `EncryptionBackend.decrypt_many(values)` — batches a list of ciphertexts. The base-class default loops sequentially; `KMSBackend` overrides with a `ThreadPoolExecutor` (max 16 workers) so a list page with N×M encrypted columns finishes in ~max RTT instead of N×M × RTT. The Billing / Bill / Receipt repositories collect every ciphertext for a list/detail query into one `decrypt_many` call before assembling the Pydantic models.

### Rollout

The idempotency contract — each backend's `is_encrypted` recognises only its own prefix — lets the three formats (raw plaintext from before this PR, `b64:v1:` from local dev, `enc:v1:` from prod KMS) coexist while the backfill runs:

1. Deploy this code with `RENTIVO_ENCRYPTION_BACKEND=base64`. New writes get `b64:v1:` prefixes; old plaintext rows still read fine.
2. Provision the KMS key (with deletion protection enabled).
3. Set `RENTIVO_ENCRYPTION_BACKEND=kms` plus the four `RENTIVO_KMS_*` values; restart.
4. Run `make backfill-encryption-dry` to preview row counts. Both raw plaintext rows AND `b64:v1:` rows are eligible (KMSBackend's `is_encrypted` returns False for both, so they get re-written through `encrypt()`).
5. Run `make backfill-encryption` to encrypt legacy rows.
6. Optionally re-run the dry-run; it should report 0 rewritten.

### Operational risks

- **KMS key deletion = permanent data loss.** Enable AWS KMS deletion protection on this key.
- **KMS outage = read failure** for encrypted rows. Direct KMS is high-SLA but does add it as a hard dependency on the read path.
- The migration `2f30089b2082_widen_pix_columns_for_encryption.py` widens the `pix_merchant_*` columns from `String(25)` / `String(15)` to `Text`. Run it during a low-traffic window on large tables.

## Decryption Cache

Decryption results are optionally cached in front of `EncryptionBackend.decrypt` / `decrypt_many` to cut KMS round-trips on hot read paths. The cache is a thin decorator (`CachingEncryptionBackend`) wrapping any concrete encryption backend; it is composed by the factory based on settings.

### Configuration

| Env var | Default | Notes |
|---|---|---|
| `RENTIVO_ENCRYPTION_CACHE_BACKEND` | `none` | `none` / `memory` / `redis` |
| `RENTIVO_ENCRYPTION_CACHE_TTL_SECONDS` | `60` | applies to memory + redis |
| `RENTIVO_ENCRYPTION_CACHE_MAX_ENTRIES` | `10000` | memory only |
| `RENTIVO_REDIS_URL` | `""` | required iff cache backend = `redis` |

Backends:

- **none** — no wrapper is constructed; behaviour identical to before this feature.
- **memory** — `cachetools.TTLCache` (bounded LRU) protected by an `RLock`, with a daemon cleanup thread that wakes every `ttl/4` seconds (floor 1s) to actively prune expired entries. Plaintext resides only in process RAM and is bounded by `max_entries`.
- **redis** — sync `redis-py`; `MGET` for batch reads, pipelined `SET ... EX ttl` for writes. Keys are `rentivo:enc:dec:v1:<sha256(ciphertext)>`. Values are plaintext, UTF-8. Failures (connection, decode) are caught and logged; reads degrade to cache miss, writes are silently dropped. Redis MUST run on a private network with authentication, and ideally TLS (`rediss://`).

Dependencies: `cachetools` is core; `redis` is in the `cache` extras group (`uv sync --extra cache`) and imported lazily inside `RedisDecryptCache`.

### What is not cached

`encrypt()` results are not cached — plaintexts rarely repeat across writes and caching them would only widen the plaintext residency window. Cache lookups are by ciphertext string only.

### Operational notes

- Set `cache_backend=none` to revert to the pre-cache code path; no migrations or KMS impact.
- The encryption test conftest (`tests/encryption/conftest.py`) calls `cache.close()` on the active `CachingEncryptionBackend` before invoking `factory._reset_for_tests()`, so the daemon cleanup thread is joined and the Redis client is closed between tests.

## Cache

A generic, reusable key→value cache (`rentivo/cache/`), pluggable across the same three backends as the decryption cache but configured by **its own env vars** — the two caches are independent toggles. Values must be JSON-serialisable (dict / list / str / int / float / bool / None) so any backend can store them; consumers serialize their own domain objects at the boundary.

| Env var | Default | Notes |
|---|---|---|
| `RENTIVO_CACHE_BACKEND` | `memory` | `none` / `memory` / `redis` |
| `RENTIVO_CACHE_TTL_SECONDS` | `60` | memory + redis |
| `RENTIVO_CACHE_MAX_ENTRIES` | `2048` | memory only |
| `RENTIVO_REDIS_URL` | `""` | shared with the decryption cache; required iff `RENTIVO_CACHE_BACKEND=redis` |

- Default is `memory` (not `none` like the decryption cache) so the cache stays on out of the box.
- `Cache` protocol (`get`/`set`/`clear`/`close`) with `NullCache`, `MemoryCache` (`cachetools.TTLCache` + `RLock` + daemon cleanup thread, stores values as-is), and `RedisCache` (JSON-encoded values, keys `rentivo:cache:v1:<sha256(key)>`, fail-open). `rentivo.cache.factory.get_cache()` returns the process-global singleton; `_reset_for_tests()` closes + drops it.
- Every backend is fail-open: a backend error degrades to a cache miss / dropped write, never a raised exception.
- Callers namespace their own keys (e.g. `billing_stats:...`) so multiple consumers can share one cache instance without collisions.
- `tests/web/conftest.py` and `tests/cache/conftest.py` call `factory._reset_for_tests()` between tests so a fresh-DB id reuse or a settings-patching test never leaks a cached value or a redis singleton.

### Consumer: billing KPI rollups

`BillingStatsService` is the first consumer. `BillingStats` (in `rentivo/services/billing_stats.py`, separate from the service) provides `to_dict`/`from_dict`; the service stores `stats.to_dict()` under key `billing_stats:{year}|{month}|{sorted billing ids}` (the YTD window + exact billing set, so entries are correct across month rollovers and shared across users since bill ids are globally unique) and rebuilds via `from_dict` on a hit.

## Bot Protection (Cloudflare Turnstile)

- Gate the public auth forms with Cloudflare Turnstile when `RENTIVO_TURNSTILE_SITE_KEY` and `RENTIVO_TURNSTILE_SECRET_KEY` are both set. If either is empty the feature is fully disabled — the loader script and widget div are not rendered, and the backend skips verification (`TurnstileService.verify` short-circuits to True).
- Verify endpoint defaults to Cloudflare's public URL; override with `RENTIVO_TURNSTILE_VERIFY_URL` if you need a self-hosted gateway.
- Service: `rentivo/services/turnstile_service.py:TurnstileService` exposes `is_enabled` and `async verify(token, remote_ip)`.
- Wired on: `/login`, `/signup`, `/forgot-password`. The form field name set by Cloudflare's widget is `cf-turnstile-response`.

## Google Authentication

- OAuth 2.0 authorization-code flow, gated by `RENTIVO_GOOGLE_AUTH_ENABLED` (default `false` — routes 404 and no button renders when off, so local dev needs no Google setup).
- `RENTIVO_GOOGLE_CLIENT_ID` and `RENTIVO_GOOGLE_CLIENT_SECRET` are required when enabled (Settings validator enforces at startup). Register `{RENTIVO_PUBLIC_APP_URL}/auth/google/callback` as the authorized redirect URI in the Google Cloud console.
- Service: `rentivo/services/google_auth_service.py:GoogleAuthService` — builds the consent URL, exchanges the code, fetches OIDC userinfo via httpx (no JWT parsing; userinfo comes over direct TLS). Routes: `web/routes/google_auth.py` (`GET /auth/google/login`, `GET /auth/google/callback`), public in `web/deps.py:PUBLIC_PREFIX_PATHS`.
- Account linking is by **verified Google email** (`email_verified` required) through the existing `users.email_hash` blind index. First Google login auto-creates a passwordless user (`password_hash=""`); `UserService.authenticate` rejects passwordless users so they can't password-login until they set one via `/forgot-password`. A duplicate-signup race is caught and falls back to logging in the existing account.
- **MFA is preserved**: the callback runs the same gate as `POST /login` — users with TOTP/passkeys get `mfa_pending_user_id` in the session and are sent to `/mfa-verify`; org MFA enforcement (`mfa_setup_required`) also applies.
- CSRF for the OAuth flow is handled with a session-bound single-use `state` parameter (compared with `secrets.compare_digest`). Audit events reuse `user.signup` / `user.login` / `mfa.challenge_issued` with `metadata.method = "google"`.

## Versioning & Releases

Rentivo follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html). Every release is a `vMAJOR.MINOR.PATCH` git tag plus a matching GitHub Release. The canonical history of releases lives in [`CHANGELOG.md`](CHANGELOG.md) using the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

### When to bump what

- **PATCH (`vX.Y.Z+1`)** — backwards-compatible bug fix, dependency bump, doc-only change, perf tweak that doesn't change behaviour. Conventional-commit prefixes that map here: `fix:`, `perf:`, `chore(deps):`, `docs:`, `refactor:` (when behaviour is identical).
- **MINOR (`vX.Y+1.0`)** — new user-visible feature or new public surface (CLI command, web route, env var, Alembic migration that *adds* a column). Backwards compatible: existing flows keep working without intervention. Prefix: `feat:`.
- **MAJOR (`vX+1.0.0`)** — breaking change. Anything that forces an operator to read release notes before deploying: removed/renamed env var, removed/renamed route, package rename, login-mechanism change, dropped Python version, Alembic migration that *drops* a column without a deprecation window. Always pair with a `BREAKING CHANGE:` footer in the merge commit so future bots can pick it up.

When in doubt, **bump higher, not lower** — an unnecessary major bump is a minor annoyance; an unexpected breaking change in a patch is an outage.

### Conventional commits

We use [Conventional Commits](https://www.conventionalcommits.org/) on PR titles and merge commits. The history from `feat(encryption): …` onward already follows this; older commits don't, and that's fine — `CHANGELOG.md` is authoritative.

```
<type>[(scope)]: <subject>

<body>

[BREAKING CHANGE: <description>]
```

Common types: `feat`, `fix`, `perf`, `refactor`, `chore`, `docs`, `test`, `ci`, `build`.

### Release procedure

1. Decide the bump (`patch`/`minor`/`major`) based on the rules above.
2. On a release branch:
   - Bump `version` in `pyproject.toml`.
   - Prepend a new section to `CHANGELOG.md` with the new version, today's date (`YYYY-MM-DD`), and grouped bullets under `### Added` / `### Changed` / `### Fixed` / `### Removed` / `### Security` (Keep-a-Changelog headings — only include groups that have entries).
3. Open a PR titled `chore(release): vX.Y.Z`, merge it.
4. Tag the merge commit and push:
   ```bash
   git checkout main && git pull
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin vX.Y.Z
   ```
5. `.github/workflows/release.yml` reads the matching `CHANGELOG.md` section and publishes the GitHub Release automatically.

### Historical tags

The 41 tags `v0.1.0` … `v3.9.0` were backfilled from git history in PR #50 (commit `405e5e3`) and now live as GitHub Releases. Use `git tag --list 'v*' | sort -V` to list them. Do **not** delete or re-create historical tags — links in PRs, issues, and external docs depend on them.

### Versioning the Docker images

Currently the Docker images aren't published to a registry — deploy is a webhook trigger (`.github/workflows/deploy.yml`). When that changes, the release workflow should also push images tagged `:vX.Y.Z` and `:latest`. Out of scope for this rollout.

## Key Rules

- **NEVER delete `invoices/`** without explicit user confirmation
- Do not use floats for monetary values — always centavos (int)
- Keep repository and storage abstractions — they exist so backends can be swapped (S3, etc.)
- Dependencies are managed with **uv**. Install with `make install` (= `uv sync --all-extras`). Run tools via `uv run` (e.g. `uv run python`, `uv run pytest`) or the equivalent `.venv/bin/` executables that `uv sync` creates — never bare `python`/`pip`/`pytest`. Add or change dependencies in `pyproject.toml`, then run `uv lock` and commit `uv.lock`.
- Always run tests in parallel: `uv run pytest -n auto` (or `make test`)
