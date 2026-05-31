# Changelog

All notable changes to Rentivo are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html). See [`CLAUDE.md` → Versioning & Releases](CLAUDE.md#versioning--releases) for the bump policy.

> Note: this changelog was seeded from 187 commits of pre-SemVer history. Some pre-v3.0.0 dates are not strictly monotonic top-to-bottom (rebase artifacts) — entries are ordered by SemVer, not by date.

## [Unreleased]
### Added
- Year-to-date KPI rollups (faturado · ano / recebido / pendente / em atraso, January through the current month in São Paulo time) and the current-bill status per property on the billings dashboard and organization detail pages. Backed by a new `BillRepository.list_summaries(billing_ids)` lightweight query (all bills per billing, no decryption) and `BillingStatsService`, which derives both the latest bill per property (table) and the YTD rollup (cards) from one query (#66).
- Generic, reusable key→value cache (`rentivo/cache/`) mirroring the decryption cache's backends — `none` / `memory` / `redis` — selected by its own `RENTIVO_CACHE_BACKEND` env (plus `RENTIVO_CACHE_TTL_SECONDS`, `RENTIVO_CACHE_MAX_ENTRIES`; Redis reuses `RENTIVO_REDIS_URL`). Values are any JSON-serialisable data; every backend is fail-open. Defaults to `memory` so it stays on out of the box. The billing KPI rollups are its first consumer (keyed `billing_stats:…`) (#66).

### Changed
- Refined neobrutalist redesign of the web UI. New design-token system in `custom.css` (OKLCH palette; Space Grotesk / Hanken Grotesk / JetBrains Mono; refined shadows) plus new components (KPI stat cards, segmented form sections, sticky action bar, org card grid, bank-style invoice document, danger zone). Legacy class names and CSS vars are preserved and restyled so every page inherits the new look. The landing, login, billing list/detail, invoice, billing create/edit, and organization list/detail/create screens were rebuilt to match the design handoff. No route or form-contract changes (#66).

## [3.10.1] - 2026-05-23
### Security
- `serialize_invite` now partial-mask redacts `invited_email` / `invited_by_email` via `PIIKind.EMAIL` and drops `organization_name` from the audit payload, matching the redaction policy already enforced by `serialize_user` / `serialize_organization`. Backfill script (`make redact-audit-logs`) extended to clean legacy invite rows (#57).
- `CSRFMiddleware` now verifies an `X-CSRF-Token` header on every non-form, non-exempt POST/PUT/DELETE/PATCH instead of silently bypassing them. JSON consumers (notably the receipts-reorder endpoint) already shipped the header; the middleware just wasn't reading it. Untokened JSON requests are now rejected with a 302 redirect + flash (#58).

### Changed
- Route-private notification helpers extracted into proper services. New `rentivo/services/billing_notification_service.py:BillingNotificationService.notify_transferred` replaces the cross-route private import of `web.routes.billing._notify_billing_transferred`. New `KnownDeviceService.notify_if_new` replaces the cross-route private import of `web.auth._check_and_send_new_device_email` (#59).
- `rentivo/repositories/sqlalchemy.py` (1634 LOC, 13 unrelated repository classes) split into a `rentivo/repositories/sqlalchemy/` subpackage with one module per entity (`billing.py`, `bill.py`, `user.py`, `organization.py`, `invite.py`, `receipt.py`, `audit_log.py`, `mfa.py`, `theme.py`, `auth.py`). The package's `__init__.py` re-exports every `SQLAlchemy*Repository` class so all ~28 existing import sites keep working unchanged (#60).
- New `web/context.py:WebActor` dataclass + `request.state.actor`, plus `AuditService.safe_log_for` / `JobService.enqueue_for` overloads that unpack the actor into the existing `source` / `actor_id` / `actor_username` kwargs. ~80 hand-derived `actor_id=user_id, actor_username=session["email"], source="web"` sites in `web/routes/` + `web/auth.py` collapsed to a single `actor=request.state.actor` argument (#61).
- `BillService` no longer holds per-request actor state in `__init__`. Methods that may enqueue PDF render jobs (`generate_bill`, `update_bill`, `regenerate_pdf`, `add_receipt`, `delete_receipt`, `reorder_receipts`) now accept an optional `actor` parameter and forward it to `JobService.enqueue_for` when provided. CLI callers omit the argument and continue rendering synchronously (#62).
- New `web/services_container.py:RequestServices` lazy per-request services container with one `@cached_property` per service, attached to `request.state.services` by a new `RequestServicesMiddleware`. The 16 `get_*_service(request)` factory functions in `web/deps.py` and the 21 function-local `from rentivo.encryption.factory import get_encryption` re-imports were deleted; routes call `request.state.services.<name>` instead. `web/deps.py` shrunk from 422 → ~250 LOC (#63).

## [3.10.0] - 2026-05-17
### Added
- Opt-in short-lived ciphertext → plaintext cache in front of `EncryptionBackend.decrypt` / `decrypt_many`, selectable via `RENTIVO_ENCRYPTION_CACHE_BACKEND` (`none` default / `memory` / `redis`). Memory backend uses `cachetools.TTLCache` with a daemon cleanup thread; Redis backend is fail-open (`MGET` reads, pipelined `SET … EX` writes, SHA-256-hashed keys under `rentivo:enc:dec:v1:`). New env vars: `RENTIVO_ENCRYPTION_CACHE_TTL_SECONDS` (default `60`), `RENTIVO_ENCRYPTION_CACHE_MAX_ENTRIES` (default `10000`, memory only), `RENTIVO_REDIS_URL` (required iff backend = `redis`). Defaults preserve pre-cache behaviour bit-for-bit (#52).

### Changed
- Web, CLI, and worker Docker images now bundle the `[cache]` extras group (`redis-py`) so `RENTIVO_ENCRYPTION_CACHE_BACKEND=redis` works out of the box on deploy (#52).

## [3.9.0] - 2026-05-12
### Added
- Encrypt `users.email` at rest behind the KMS backend; introduce a `users.email_hash` HMAC blind-index column for `WHERE email = ?` lookups (#49).

## [3.8.0] - 2026-05-04
### Added
- Encrypt `billings.name` (#47).

## [3.7.1] - 2026-05-04
### Changed
- `EncryptionBackend.decrypt_many` batches list-page decryptions through a 16-worker `ThreadPoolExecutor` so N×M encrypted columns finish in ~max RTT instead of N×M × RTT (#48).

## [3.7.0] - 2026-05-04
### Added
- Extend KMS field encryption to free-text PII columns across `billings`, `billing_items`, `bills`, `bill_line_items`, and `receipts`. Run `make backfill-encryption` after deploy to rewrite legacy rows (#46).

## [3.6.2] - 2026-05-04
### Fixed
- `bills` POST now enqueues a `pdf.render` job instead of rendering the invoice PDF inline, so the request returns immediately (#44).

## [3.6.1] - 2026-05-03
### Fixed
- Redact PIX values from `audit_logs.previous_state` / `new_state` JSON before insert, and backfill legacy rows via `make redact-audit-logs` (#43).

## [3.6.0] - 2026-05-03
### Added
- KMS field encryption for PIX columns and TOTP secrets across `users`, `organizations`, `billings`, `user_totp`. New `RENTIVO_ENCRYPTION_BACKEND` env var (`base64` | `kms`) (#42).

## [3.5.0] - 2026-05-03
### Security
- FastAPI security audit + regression guards (#41).

## [3.4.0] - 2026-05-02
### Added
- `pdf.render` background job + bulk regenerate via queue, with a "Renderizando" UI badge on bills awaiting render (#38, #39).

## [3.3.0] - 2026-05-02
### Added
- `s3.delete` background job — closes orphan-leak gaps when bills or receipts are deleted (#37).

## [3.2.0] - 2026-05-02
### Added
- Durable background email queue + dedicated worker container (`Dockerfile.worker`) (#36).

## [3.1.0] - 2026-05-01
### Added
- Transactional emails for auth, MFA, devices, organization invites, and billing transfers (#35).

## [3.0.0] - 2026-05-01
### Added
- SES-backed password recovery (`/forgot-password`, `/reset-password`) (#34).

### Changed
- **BREAKING**: login is now email-only. The `username` column is no longer used for authentication; existing users must log in with their email.

### Migration notes
- Run `make migrate` to apply the schema changes.
- Set `RENTIVO_EMAIL_BACKEND` (`local` | `ses`) and `RENTIVO_SES_*` env vars before enabling the SES backend.

## [2.12.0] - 2026-04-23
### Changed
- Bump Python base image from `3.10-slim` to `3.14-slim`; switch containers to non-root user; add restart policy (#22, #30).

## [2.11.0] - 2026-04-23
### Added
- Dependabot for pip, GitHub Actions, and Docker (#18, weekly schedule, America/Sao_Paulo timezone).

## [2.10.0] - 2026-04-23
### Added
- `/health` liveness endpoint (#17).

## [2.9.0] - 2026-04-19
### Added
- Google Tag Manager analytics, gated by `RENTIVO_GTM_CONTAINER_ID`. No script tags, network calls, or cookies when unset (#16).

## [2.8.0] - 2026-04-19
### Security
- Cross-user authorization checks across bill edit, bill delete, receipt upload/delete, PDF regenerate, passkey CSRF, and the `next` redirect param (#9–#15).

## [2.7.0] - 2026-04-19
### Changed
- Store PIX config per user / organization / billing instead of reading from env (#8).

## [2.6.0] - 2026-04-19
### Added
- SEO metadata, `sitemap.xml`, `robots.txt` (#7).

## [2.5.0] - 2026-04-19
### Changed
- Adopt structlog for structured, contextual logging (#6).

## [2.4.0] - 2026-04-19
### Security
- Harden auth, PIX handling, storage, and money rounding (#5).

## [2.3.0] - 2026-02-16
### Added
- Audit logging across web and CLI state-changing operations.
- Receipt attachments (PDF/JPEG/PNG, max 10 MB) merged into the generated invoice PDF.

## [2.2.0] - 2026-02-13
### Added
- Organizations + invites with ownership and RBAC (owner / admin / manager / viewer) (#2).

## [2.1.0] - 2026-02-28
### Added
- MFA: TOTP + Passkey (WebAuthn) registration and challenge flows (#3).

## [2.0.0] - 2026-02-17
### Changed
- **BREAKING**: project renamed from Landlord to Rentivo. Python package, CLI entry point, env-var prefix, and config files all changed (`LANDLORD_*` → `RENTIVO_*`).

### Migration notes
- Rename your `.env` keys from `LANDLORD_*` to `RENTIVO_*`.
- Reinstall the package and update any scripts that called `landlord` to call `rentivo`.

## [1.9.0] - 2026-02-09
### Changed
- Deploy workflow now gates on `pytest` success and uploads coverage to Codecov.

## [1.8.0] - 2026-02-09
### Changed
- Replace Bootstrap with a neobrutalist design system built from scratch.

## [1.7.0] - 2026-02-08
### Added
- Unit test suite: 286 tests, 97% coverage (#1).

## [1.6.0] - 2026-02-08
### Added
- Configurable storage prefix for S3 and local keys.

## [1.5.0] - 2026-02-08
### Added
- Bill soft delete + UUID-based routes + ULID identifier generation.

## [1.4.0] - 2026-02-08
### Added
- Extra-expenses support on the bill edit page.

## [1.3.0] - 2026-02-08
### Changed
- All generated timestamps now use the `America/Sao_Paulo` timezone, including overdue checks.

## [1.2.0] - 2026-02-08
### Added
- Payment tracking for bills with paid / pending / overdue status.

## [1.1.0] - 2026-02-07
### Added
- Change-password flow in both CLI and web.

## [1.0.0] - 2026-02-07
### Changed
- **BREAKING**: replace Django with FastAPI for the web UI. Adds user management, session middleware, and a from-scratch template layer.

### Migration notes
- Drop the Django settings module; configure via `RENTIVO_*` env vars (later renamed in v2.0.0).
- Run `make migrate` to align Alembic migrations.

## [0.5.0] - 2026-02-07
### Added
- Django web app with models, views, and templates (later replaced by FastAPI in v1.0.0).

## [0.4.0] - 2026-02-07
### Added
- `due_date` field on bills/invoices.
- GitHub Actions deploy workflow (webhook trigger).

## [0.3.0] - 2026-02-07
### Added
- Billing update support: edit PIX key and line items.

## [0.2.0] - 2026-02-07
### Changed
- Public release: project renamed to `landlord-cli`, README rewritten.

## [0.1.0] - 2026-02-07
### Added
- Initial commit: apartment billing generator with SQLAlchemy repositories.

[Unreleased]: https://github.com/jorgejr568/rentivo/compare/v3.9.0...HEAD
[3.9.0]: https://github.com/jorgejr568/rentivo/compare/v3.8.0...v3.9.0
[3.8.0]: https://github.com/jorgejr568/rentivo/compare/v3.7.1...v3.8.0
[3.7.1]: https://github.com/jorgejr568/rentivo/compare/v3.7.0...v3.7.1
[3.7.0]: https://github.com/jorgejr568/rentivo/compare/v3.6.2...v3.7.0
[3.6.2]: https://github.com/jorgejr568/rentivo/compare/v3.6.1...v3.6.2
[3.6.1]: https://github.com/jorgejr568/rentivo/compare/v3.6.0...v3.6.1
[3.6.0]: https://github.com/jorgejr568/rentivo/compare/v3.5.0...v3.6.0
[3.5.0]: https://github.com/jorgejr568/rentivo/compare/v3.4.0...v3.5.0
[3.4.0]: https://github.com/jorgejr568/rentivo/compare/v3.3.0...v3.4.0
[3.3.0]: https://github.com/jorgejr568/rentivo/compare/v3.2.0...v3.3.0
[3.2.0]: https://github.com/jorgejr568/rentivo/compare/v3.1.0...v3.2.0
[3.1.0]: https://github.com/jorgejr568/rentivo/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/jorgejr568/rentivo/compare/v2.12.0...v3.0.0
[2.12.0]: https://github.com/jorgejr568/rentivo/compare/v2.11.0...v2.12.0
[2.11.0]: https://github.com/jorgejr568/rentivo/compare/v2.10.0...v2.11.0
[2.10.0]: https://github.com/jorgejr568/rentivo/compare/v2.9.0...v2.10.0
[2.9.0]: https://github.com/jorgejr568/rentivo/compare/v2.8.0...v2.9.0
[2.8.0]: https://github.com/jorgejr568/rentivo/compare/v2.7.0...v2.8.0
[2.7.0]: https://github.com/jorgejr568/rentivo/compare/v2.6.0...v2.7.0
[2.6.0]: https://github.com/jorgejr568/rentivo/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/jorgejr568/rentivo/compare/v2.4.0...v2.5.0
[2.4.0]: https://github.com/jorgejr568/rentivo/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/jorgejr568/rentivo/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/jorgejr568/rentivo/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/jorgejr568/rentivo/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/jorgejr568/rentivo/compare/v1.9.0...v2.0.0
[1.9.0]: https://github.com/jorgejr568/rentivo/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/jorgejr568/rentivo/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/jorgejr568/rentivo/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/jorgejr568/rentivo/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/jorgejr568/rentivo/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/jorgejr568/rentivo/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/jorgejr568/rentivo/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/jorgejr568/rentivo/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/jorgejr568/rentivo/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/jorgejr568/rentivo/compare/v0.5.0...v1.0.0
[0.5.0]: https://github.com/jorgejr568/rentivo/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/jorgejr568/rentivo/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/jorgejr568/rentivo/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/jorgejr568/rentivo/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jorgejr568/rentivo/releases/tag/v0.1.0
