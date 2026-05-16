# Changelog

All notable changes to Rentivo are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html). See [`CLAUDE.md` → Versioning & Releases](CLAUDE.md#versioning--releases) for the bump policy.

## [Unreleased]

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
- Extend KMS field encryption to free-text PII columns (`billings.description`, `billing_items.description`, `bills.notes`, `bill_line_items.description`, `receipts.filename`, etc.) (#46).

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
### Changed
- **BREAKING**: login is now email-only. The `username` column is no longer used for authentication; existing users must log in with their email.
- Adds SES-backed password recovery (`/forgot-password`, `/reset-password`) (#34).

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

[Unreleased]: https://github.com/jorgejr568/landlord-cli/compare/v3.9.0...HEAD
[3.9.0]: https://github.com/jorgejr568/landlord-cli/compare/v3.8.0...v3.9.0
[3.8.0]: https://github.com/jorgejr568/landlord-cli/compare/v3.7.1...v3.8.0
[3.7.1]: https://github.com/jorgejr568/landlord-cli/compare/v3.7.0...v3.7.1
[3.7.0]: https://github.com/jorgejr568/landlord-cli/compare/v3.6.2...v3.7.0
[3.6.2]: https://github.com/jorgejr568/landlord-cli/compare/v3.6.1...v3.6.2
[3.6.1]: https://github.com/jorgejr568/landlord-cli/compare/v3.6.0...v3.6.1
[3.6.0]: https://github.com/jorgejr568/landlord-cli/compare/v3.5.0...v3.6.0
[3.5.0]: https://github.com/jorgejr568/landlord-cli/compare/v3.4.0...v3.5.0
[3.4.0]: https://github.com/jorgejr568/landlord-cli/compare/v3.3.0...v3.4.0
[3.3.0]: https://github.com/jorgejr568/landlord-cli/compare/v3.2.0...v3.3.0
[3.2.0]: https://github.com/jorgejr568/landlord-cli/compare/v3.1.0...v3.2.0
[3.1.0]: https://github.com/jorgejr568/landlord-cli/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/jorgejr568/landlord-cli/compare/v2.12.0...v3.0.0
[2.12.0]: https://github.com/jorgejr568/landlord-cli/compare/v2.11.0...v2.12.0
[2.11.0]: https://github.com/jorgejr568/landlord-cli/compare/v2.10.0...v2.11.0
[2.10.0]: https://github.com/jorgejr568/landlord-cli/compare/v2.9.0...v2.10.0
[2.9.0]: https://github.com/jorgejr568/landlord-cli/compare/v2.8.0...v2.9.0
[2.8.0]: https://github.com/jorgejr568/landlord-cli/compare/v2.7.0...v2.8.0
[2.7.0]: https://github.com/jorgejr568/landlord-cli/compare/v2.6.0...v2.7.0
[2.6.0]: https://github.com/jorgejr568/landlord-cli/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/jorgejr568/landlord-cli/compare/v2.4.0...v2.5.0
[2.4.0]: https://github.com/jorgejr568/landlord-cli/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/jorgejr568/landlord-cli/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/jorgejr568/landlord-cli/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/jorgejr568/landlord-cli/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/jorgejr568/landlord-cli/compare/v1.9.0...v2.0.0
[1.9.0]: https://github.com/jorgejr568/landlord-cli/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/jorgejr568/landlord-cli/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/jorgejr568/landlord-cli/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/jorgejr568/landlord-cli/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/jorgejr568/landlord-cli/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/jorgejr568/landlord-cli/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/jorgejr568/landlord-cli/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/jorgejr568/landlord-cli/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/jorgejr568/landlord-cli/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/jorgejr568/landlord-cli/compare/v0.5.0...v1.0.0
[0.5.0]: https://github.com/jorgejr568/landlord-cli/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/jorgejr568/landlord-cli/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/jorgejr568/landlord-cli/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/jorgejr568/landlord-cli/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jorgejr568/landlord-cli/releases/tag/v0.1.0
