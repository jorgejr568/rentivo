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
- Serializers in `rentivo/services/audit_serializers.py` strip sensitive fields (`password_hash`)
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

## Key Rules

- **NEVER delete `invoices/`** without explicit user confirmation
- Do not use floats for monetary values — always centavos (int)
- Keep repository and storage abstractions — they exist so backends can be swapped (S3, etc.)
- Always use `.venv/bin/` commands (e.g. `.venv/bin/python`, `.venv/bin/pip`, `.venv/bin/pytest`) instead of bare `python`/`pip`/`pytest`
- Always run tests in parallel: `.venv/bin/python -m pytest -n auto` (or `make test`)
