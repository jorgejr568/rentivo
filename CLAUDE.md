# Rentivo

Apartment billing management with PDF invoice generation — FastAPI web UI.

## Running

```bash
# Start MariaDB (required)
docker compose up -d db

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
- **`Dockerfile.worker`** — Background job worker (`python -m rentivo.workers`; handlers: `email.send`, `pdf.render`, `recibo.render`, `s3.delete`, `communication.send`, `export.generate`)

```bash
# Web container (default)
make build       # build web image
make up          # start web container (port 8000)
make down        # stop and remove
make restart     # down + up
make logs        # tail logs
make health      # curl http://localhost:8000

# Docker Compose (full stack: db, web, worker)
make compose-up            # start the full stack
make compose-down          # stop all
make compose-createuser    # create web user
make compose-dev           # dev stack with bind mounts + web live reload
make worker                # run the job worker locally

# Worker container
make build-worker / up-worker / down-worker / logs-worker / shell-worker
```

## Architecture

- **Settings**: `rentivo/settings.py` — Pydantic Settings, env prefix `RENTIVO_`, reads `.env`
- **Database**: `rentivo/db.py` — SQLAlchemy engine + connection to MariaDB. Schema managed by Alembic. Configured via `RENTIVO_DB_URL`
- **Repositories**: `rentivo/repositories/` — Abstract base classes in `base.py`, SQLAlchemy Core impl in `sqlalchemy.py`, factory in `factory.py`
- **Storage**: `rentivo/storage/` — Same pattern. `LocalStorage` writes to `./invoices/`, `S3Storage` uploads to a private bucket with presigned URLs. Configurable via `RENTIVO_STORAGE_BACKEND`
- **PDF**: `rentivo/pdf/invoice.py` — fpdf2-based invoice with navy/green color palette; `rentivo/pdf/merger.py` — merges receipt attachments into invoices using pypdf
- **Services**: `rentivo/services/` — Business logic layer wiring repos + storage + PDF

## Documentation Map

- `docs/configuration.md` — full env var reference (guarded by `tests/test_env_example.py`; update both together with `rentivo/settings.py`)
- `docs/development.md` — dev setup (local + compose-only), worker, troubleshooting
- `CONTRIBUTING.md` — contributor workflow; `SECURITY.md` — vulnerability reporting
- When adding/renaming a Settings field: update `.env.example` AND `docs/configuration.md`, or the test suite fails.

## S3 Storage

- Invoice S3 key pattern: `{billing_uuid}/{bill_uuid}.pdf`
- Receipt S3 key pattern: `{billing_uuid}/{bill_uuid}/receipts/{receipt_uuid}{ext}`
- `pdf_path` column stores the S3 key, not a URL
- Presigned URLs (7-day expiry) are generated on the fly via `get_invoice_url()` / `get_presigned_url()`
- Set `RENTIVO_STORAGE_BACKEND=s3` and configure `RENTIVO_S3_*` env vars

## Conventions

- All customer-facing text (web templates, PDF content) in **PT-BR**
- Currency in **BRL** (R$), formatted via `rentivo.models.format_brl()`
- Money stored as **centavos (int)** in the database — never use floats for money
- Code (variable names, comments) in English

## FastAPI Web App

The `web/` directory contains a FastAPI web application that provides a browser-based UI for managing billings, bills, and invoices.

### Running

```bash
make migrate             # run Alembic migrations (creates users table etc.)
make web-createuser      # create web login user
make web-run             # start uvicorn at http://localhost:8000
```

### Architecture

- **App**: `web/app.py` — FastAPI app, SessionMiddleware, Jinja2 templates, static files
- **Auth**: `web/auth.py` — login/logout routes, session-based auth
- **Login flow**: `web/login_flow.py` — `complete_login()` / `begin_mfa_challenge()`, the shared post-credential sequence used by password, TOTP/recovery, passkey, and Google logins
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
| `POST /billings/<id>/attachments/upload` | Upload a billing document (name + file) |
| `GET /billings/<id>/attachments/<att_id>` | Download a billing document |
| `POST /billings/<id>/attachments/<att_id>/delete` | Delete a billing document |
| `/login` | Login page |
| `/logout` | Logout |
| `/change-password` | Change password |

## Receipt Attachments

- Bills can have attached receipt files (PDF, JPEG, PNG, max 10 MB)
- Receipt storage key pattern: `{billing_uuid}/{bill_uuid}/receipts/{receipt_uuid}{ext}`
- Receipts are merged into the generated PDF invoice using pypdf (appended after invoice pages, in order of addition)
- Model: `rentivo/models/receipt.py`, Repository: `ReceiptRepository`, Service: integrated into `BillService`
- Upload/delete via separate forms on the bill edit page

## Payment Receipt (Recibo de Pagamento)

- A **recibo** is a quittance PDF (`rentivo/pdf/recibo.py:ReciboPDF`) issued for a **PAID** bill — distinct from both the invoice and the bill-level `receipt` attachments. Naming is deliberately kept apart (`recibo` ≠ `receipt`).
- **Lifecycle is driven by `BillService.change_status`** (the single status-change path, called from `web/routes/bill.py`):
  - entering PAID (from any non-PAID status) enqueues a `recibo.render` job (web) or renders synchronously (CLI, no JobService);
  - leaving PAID enqueues an `s3.delete` for the stored key and NULLs `bills.recibo_pdf_path` — the quittance must not outlive the payment it certifies. Re-saving PAID is a no-op.
- `recibo.render` handler (`rentivo/jobs/handlers/recibo.py`) re-checks `status == PAID` before rendering (status may revert before the job runs) → no orphan recibo for an unpaid bill.
- Storage key pattern: `{billing_uuid}/{bill_uuid}.recibo.pdf`; the key is stored in the `bills.recibo_pdf_path` column (Alembic `08c21e96caa6`). `BillService.store_recibo` renders + persists + records the key; `_remove_recibo` tears it down. `StorageCleanupService.enqueue_bill_delete_cascade` also deletes the recibo key.
- Download: `GET …/recibo` (PAID-only). Serves the stored object when present; falls back to on-the-fly rendering during the brief render window or if the worker is behind, so the download never breaks. Audit `bill.recibo_download`; GTM `rentivo_recibo_downloaded` (hashed uuid).
- Send: the recibo can be e-mailed to billing recipients as a communication of type `payment_receipt` (see Tenant Communications).

## Billing Attachments

- Billings can carry named documents (e.g. a lease contract) — separate from bill-level receipts and **never merged into a bill PDF**.
- Model: `rentivo/models/billing_attachment.py` (`BillingAttachment`, with a user-given `name` plus the original `filename`; both KMS-encrypted). Allowed types PDF/JPEG/PNG, max 10 MB. A blank `name` defaults to the filename.
- Storage key pattern: `{billing_uuid}/attachments/{attachment_uuid}{ext}`.
- Repository: `BillingAttachmentRepository` / `SQLAlchemyBillingAttachmentRepository`. Service: `BillingAttachmentService` (repo + storage). Wired in `web/services_container.py` as `billing_attachment`.
- Routes on the billing router (`web/routes/billing.py`): `POST /billings/<id>/attachments/upload` (single file + name), `GET /billings/<id>/attachments/<att_id>` (download), `POST /billings/<id>/attachments/<att_id>/delete`. Upload/delete need `edit`; download needs `view`.
- UI: upload + list + delete panel on the billing edit page; read-only download list on the billing detail page.
- Audit events: `attachment.upload`, `attachment.delete` (serializer omits `storage_key`). GTM: `rentivo_billing_attachment_uploaded/deleted`. Deleting a billing cascades attachment-file cleanup via `StorageCleanupService.enqueue_billing_delete_cascade` (which requires an `attachment_repo`).

## Bill Export

- A billing's bills can be exported as **CSV or XLSX** for accounting. Export runs in the background and is emailed — it is NOT a synchronous download.
- Trigger: `POST /billings/<id>/bills/export` (form `format=csv|xlsx`, default/fallback csv; needs `view`). Buttons live on the billing detail page. The route guards that the billing has at least one recipient (else redirects to the edit page), then enqueues one `export.generate` job and flashes "exportação iniciada".
- Worker handler `rentivo/jobs/handlers/export.py:handle_export_generate` (payload `{billing_id, format}`): loads the billing + bills + recipients, builds rows via `ExportService`, serializes via `rentivo/export/serializers.py:serialize_rows` (returns `(body, content_type, ext)`; csv fallback), and sends **one email per recipient — never CC** with the file attached (event `export_ready`). Recipient name/email resolve fresh from the encrypted `billing_recipients` rows, so no PII rides in the job payload. At-least-once: a mid-batch crash retries the whole send (a duplicate accounting export is benign).
- `ExportService` (`rentivo/services/export_service.py`) is FastAPI-free row building: PT-BR headers, a numeric `Valor (R$)` column (centavos/100) plus a formatted `R$` column. Serializers neutralize spreadsheet **formula injection** (cells starting with `= + - @ \t \r` get a leading `'`). `export_filename`/`export_slug` build an accent-folded slug filename (`São João` → `faturas_sao-joao.csv`).
- `EmailService.send(..., attachments=...)` carries the generated file; templates `web/templates/emails/export_ready.{html,txt}` (PT-BR). The `From` uses the SES default (transactional), not the communications override.
- Audit event: `billing.export` (`new_state={format, recipient_count}`). GTM: `rentivo_data_exported`. Temporal: `ExportGenerateWorkflow` + `export.generate` activity wrap the same registry handler.
- Dependency: **openpyxl** (XLSX).

## Audit Logging

- **AuditService** logs all state-changing operations across the web app and maintenance scripts
- Event types defined in `rentivo/models/audit_log.py` (`AuditEventType`)
- Serializers in `rentivo/services/audit_serializers.py` strip sensitive fields (`password_hash`) and partial-mask redact PII via `rentivo/pii_redaction.py:redact()`. PIX fields (`pix_key`, `pix_merchant_name`, `pix_merchant_city`) and `to_email` in `email.send` job payloads are stored under their original field names with masked values: PIX fields show first 3 chars + `...` + last 2 (e.g. `123...01`); emails show first 2 chars of local + `...@` + full domain (e.g. `jo...@gmail.com`). Short values collapse to `***`. The mask is one-way, key-less, and deterministic — no `secret_key` dependency, no per-environment correlation key. Reviewers can recognize "same value across rows" via equal masked strings without seeing the plaintext.
- Backfill: `make redact-audit-logs-dry` previews; `make redact-audit-logs` rewrites legacy `audit_logs` rows whose JSON still contains plaintext PII. Idempotent (the redaction function is its own fixed point on typical inputs). Run once after deploying the redacted serializers.
- `safe_log()` swallows exceptions — audit failures never block business operations
- Web routes: actor context comes from session (`user_id`, `username`)
- Maintenance scripts (e.g. `regenerate_pdfs`): use `source="cli"`, `actor_id=None`, `actor_username=""`
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
- **Business** — `rentivo_bill_generated`, `rentivo_billing_created/edited/deleted/transferred`, `rentivo_bill_*`, `rentivo_invoice_downloaded`, `rentivo_recibo_downloaded`, `rentivo_receipt_uploaded/deleted`, `rentivo_billing_attachment_uploaded/deleted`, `rentivo_login_success/failed`, `rentivo_logout`, `rentivo_signup_completed`, `rentivo_password_changed`, `rentivo_mfa_*`, `rentivo_passkey_*`, `rentivo_organization_created`, `rentivo_invite_*`, `rentivo_theme_changed`, `rentivo_communication_sent`, `rentivo_data_exported`.

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

## Tenant Communications

- Billings carry **recipients** (`billing_recipients`, encrypted `name` + `email`). Multiple per billing; each send goes to one recipient — never CC. Managed via a formset on the billing edit page (`RecipientService.replace_for_billing`).
- **Reply-To**: billings also carry an optional **reply-to** contact list (`billing_reply_to`, encrypted `name` + `email`) managed by a second formset on the billing create/edit forms (`RecipientService` reused over `SQLAlchemyReplyToRecipientRepository`). At send time the `communication.send` handler formats each as `Name <email>` (`email.utils.formataddr`) and sets the email `Reply-To` header — resolved fresh from the billing at send time, NOT snapshotted onto the communication row. Audit event: `billing.reply_to_updated`.
- **From override**: `RENTIVO_COMMUNICATIONS_FROM_EMAIL` (optional) overrides the `From` for communication emails only; empty falls back to `RENTIVO_SES_FROM_EMAIL` then `noreply@localhost`. Account/security/transactional emails always use `RENTIVO_SES_FROM_EMAIL`.
- **Templates** (`communication_templates`) are polymorphic-owned (`owner_type` ∈ `user` | `organization` | `billing`) per `comm_type`, unique on `(owner_type, owner_id, comm_type)` (`uq_comm_template_owner`). `CommunicationService.resolve_template` resolves most-specific-first: billing → billing owner (user/org) → system default (`rentivo/communications/defaults.py`, seeded from the landlord's PT-BR copy; the synthetic fallback uses `owner_type='system'` / `owner_id=0` and is never persisted). Encrypted `subject` + `body_markdown`.
- **Bodies are Markdown**, rendered by `rentivo/communications/render.py:render_markdown` with `markdown-it-py` and raw HTML disabled (`MarkdownIt("commonmark", {"html": False})`) — `<tag>` in the source is escaped to inert text, so user input can never inject live HTML. Placeholders (PT-BR): `{{nome_inquilino}}` (recipient name), `{{unidade}}` (billing name), `{{mes}}` (e.g. "maio de 2026", via `month_long`), `{{vencimento}}` (due date), `{{total}}` (BRL). Substituted at send time and snapshotted onto the communication row; unknown tokens are left verbatim.
- **Comm types** are the `CommType` enum (`rentivo/models/communication.py`): `bill_ready` (attaches the invoice PDF) and `payment_receipt` (attaches the stored **recibo** PDF, PAID bills only). Each has its own system-default template. The compose/send routes take the type **explicitly** (`?type=…` on compose, hidden `comm_type` field on send) and validate it strictly via `CommType(...)` — an unknown value is rejected (flash redirect), never silently defaulted, so a bad value can't send the wrong document. The `communication.send` handler branches on `comm.comm_type` to pick invoice-vs-recibo (`fatura-…pdf` / `recibo-…pdf`) and fails permanently if the chosen document is absent.
- **Sends** are manual: compose/preview on the bill page (`web/routes/communication.py`, router prefix `/billings/{billing_uuid}/bills/{bill_uuid}/communications`: `GET /compose`, `POST /preview`, `POST /send`), then one `communication.send` job per recipient. The handler (`rentivo/jobs/handlers/communication.py`) renders the stored row, attaches the bill/recibo PDF, sends one email, and marks the row `sent`; the registered `register_on_fail` dead-letter hook marks it `failed`.
- **Communications** (`communications`, the sent log; encrypted `recipient_name` / `recipient_email` / `subject` / `body_markdown`) are listed on the bill page with status (`queued` / `sent` / `failed`). Audit events: `communication.sent`, `communication.template_saved`, `billing.recipients_updated`. GTM: `rentivo_communication_sent`.
- Email attachments: `EmailAttachment` on `EmailMessage`; `rentivo/email/mime.py:build_mime` is shared by the local backend and SES. SES switches to `send_raw_email` only when attachments are present, preserving `ConfigurationSetName`.
- **Content guardrails**: `rentivo/communications/moderation.py:scan(text)` does a tiered, in-process PT-BR lexicon scan (no external API/LLM, deterministic; `_normalize` handles accents/leetspeak/repeated-chars/whitespace, word-token matching for the word lists and normalized-substring matching for phrases). `POST /send` is the authoritative gate: SEVERE (slurs/hate/threats) is blocked (no communication row, no job; audit `communication.blocked`); MILD (profanity) requires an explicit `acknowledge_warning` checkbox (audit `communication.flagged_override`). `POST /preview` returns `{html, severe, mild}` to drive the compose-page moderation panel. Audit `new_state` stores counts (`severe_count`/`mild_count`), never the flagged words.
- **Sender attribution**: a non-editable system block after the body in `communication.html`/`.txt` — "Enviado por {remetente} através do Rentivo." followed by "O conteúdo desta mensagem é de responsabilidade do remetente, não do Rentivo." The sender name is resolved fresh in the `communication.send` handler (`_resolve_sender_name`): organization name for org-owned billings, account email for user-owned, generic "o responsável" fallback. Threaded via `EmailService.send_communication(..., sender_name=...)`; autoescaped (only `body_html` is `| safe`).
- Dependency: `markdown-it-py` (core).

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
| `billing_recipients` | `name`, `email` |
| `billing_reply_to` | `name`, `email` |
| `communication_templates` | `subject`, `body_markdown` |
| `communications` | `recipient_name`, `recipient_email`, `subject`, `body_markdown` |
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

## Observability (OpenTelemetry Tracing)

Optional distributed tracing, off by default. One module — `rentivo/observability/tracing.py` — owns every `opentelemetry` import behind a `try/except ImportError`; when the `otel` extra is absent or `RENTIVO_OTEL_ENABLED=false`, the global tracer is `None` and `traced` / `span` / `set_attributes` / `inject_context` / `extract_context` all no-op.

- **Enable:** the runtime Docker images already bundle the `otel` extra; for host runs `uv sync --extra otel`. Set `RENTIVO_OTEL_ENABLED=true` + `RENTIVO_OTEL_EXPORTER_OTLP_ENDPOINT` (OTLP/HTTP, the SDK appends `/v1/traces`). Four settings: `RENTIVO_OTEL_ENABLED`, `RENTIVO_OTEL_SERVICE_NAME`, `RENTIVO_OTEL_EXPORTER_OTLP_ENDPOINT`, `RENTIVO_OTEL_SAMPLE_RATIO`.
- **Instrument anything** with `@traced("name")` (sync or async; defaults to the bare function name). Sub-spans via `with span("name"):`. Dynamic non-PII attributes via `set_attributes(...)`.
- **Root spans:** the outermost pure-ASGI `TracingMiddleware` (`rentivo/observability/middleware.py`) opens `HTTP <method>`; the worker opens `job <type>`. Decorated calls + SQL spans nest automatically through OpenTelemetry's active-span contextvar.
- **Cross-process nesting:** `JobService.enqueue` injects a W3C `traceparent` into the payload's `_otel` key; `Worker._run_one` extracts it so worker spans re-parent onto the enqueuing request.
- **DB spans:** `instrument_sqlalchemy(engine)` (wired into `db.get_engine()`) emits a span per SQL statement via `SQLAlchemyInstrumentor`, handed our provider explicitly (no global provider is installed). Bound params are omitted (PII-safe).
- **Instrumented (comprehensive):** every SQL statement; every public **service** method (`<entity>.<method>`) and **repository** method (`<entity>_repo.<method>`); auth incl. `auth.verify_password` (bcrypt) and `login.*`; encryption (`base64.*`, `kms.*`, `cache.*`), storage (`local.*`, `s3.*`), email (`ses.send`, `email.*`), and PDF (`pdf.*`). Adding `@traced` is coverage-neutral (decorator internals are tested in `tracing.py`; bodies still run via the disabled path).
- **Span volume:** deep instrumentation = many spans/request (e.g. `base64.decrypt` per encrypted field). Tune with `RENTIVO_OTEL_SAMPLE_RATIO` (parent-based head sampling).
- **Privacy:** never put PII in span attributes — non-PII only (method/path, job type/ulid, counts, sizes, backend names). Span names are static; SQL spans omit bound params.
- **Local Jaeger:** `make jaeger-up` (compose profile `observability`, opt-in), UI at http://localhost:16686, endpoint `http://jaeger:4318` on the compose network. Full guide: `docs/observability.md`.
- Tests assert spans with `InMemorySpanExporter`; `tests/observability/conftest.py` provides `reset_tracing` (autouse) + `span_exporter`. Other test packages re-export those fixtures via a one-line conftest. The coverage env runs `uv sync --all-extras`, so the otel branches execute (only the `except ImportError` guard carries `# pragma: no cover`).

## Job Drivers

Background jobs run through a pluggable driver selected by `RENTIVO_JOB_BACKEND` (`database` default | `temporal`). The producer seam is `rentivo/jobs/backend.py:JobBackend.enqueue`; `JobService` depends on it. `rentivo/jobs/factory.py:get_job_backend(conn)` dispatches.

- **database** — `DatabaseJobBackend` over `SQLAlchemyJobRepository`; the polling `Worker` (`rentivo/jobs/worker.py`) drains the `jobs` table. Zero extra deps; the supported production default.
- **temporal** (optional, `temporal` extra; NOT required even in production) — `TemporalJobBackend` starts one workflow per enqueue. Per-job-type workflows/activities in `rentivo/jobs/temporal/` wrap the **unchanged** registry handlers. The workflow retry loop mirrors the DB backoff (`rentivo/jobs/backoff.py`, 60s/5m/15m/1h/6h, max 5), maps `PermanentJobError` → non-retryable, and fires the same fail-hooks + `JOB_*` audit events via the `rentivo.finalize_job` activity. OTel `_otel` carrier propagates identically.
- Worker entrypoint `python -m rentivo.workers` dispatches on the backend. Local Temporal: `make temporal-up` (opt-in compose profile). Shared backoff lives in `rentivo/jobs/backoff.py`. Full guide: `docs/jobs.md`.

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
- Dependencies are managed with **uv**. Install with `make install` (= `uv sync --all-extras`). Run tools via `uv run` (e.g. `uv run python`, `uv run pytest`, `uv run ruff`) — never bare `python`/`pip`/`pytest`. Add or change dependencies in `pyproject.toml`, then run `uv lock` and commit `uv.lock`.
- Always run tests in parallel: `uv run pytest -n auto` (or `make test`)
