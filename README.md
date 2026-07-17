<h1 align="center">Rentivo</h1>

<p align="center">
  Apartment billing management with PDF invoice generation — <strong>Web UI</strong>
</p>

<p align="center">
  <a href="https://github.com/jorgejr568/rentivo/actions/workflows/deploy.yml"><img src="https://github.com/jorgejr568/rentivo/actions/workflows/deploy.yml/badge.svg" alt="CI"></a>
  <a href="https://codecov.io/gh/jorgejr568/rentivo"><img src="https://codecov.io/gh/jorgejr568/rentivo/branch/main/graph/badge.svg" alt="codecov"></a>
  <a href="https://github.com/jorgejr568/rentivo/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue" alt="GPL-3.0"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.14+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/MariaDB-11-003545?logo=mariadb&logoColor=white" alt="MariaDB">
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/SQLAlchemy-Core-D71F00?logo=sqlalchemy&logoColor=white" alt="SQLAlchemy">
</p>

---

Built for Brazilian landlords — all tenant-facing output is in **PT-BR** with **BRL (R$)** currency and **PIX QR codes** on invoices.

## Features

- Recurring billing templates with multiple line items; one-click monthly bill generation
- Professional PDF invoices with PIX QR codes; receipt attachments (PDF/JPG/PNG) merged into the invoice
- **Web UI** (FastAPI) over a clean repository + service layer
- Login with sessions, **TOTP MFA and passkeys (WebAuthn)**, password recovery by email
- **Organizations** with role-based access (owner / admin / manager / viewer) and email invites
- Transactional emails (AWS SES, or local `.eml` files in dev)
- **Background job worker** for emails, PDF rendering, and storage cleanup
- Field-level **encryption of PII at rest** (AWS KMS) with an email blind index
- Comprehensive **audit logging** with PII redaction
- Invoice storage on local disk or **S3** with presigned URLs
- Optional bot protection (Cloudflare Turnstile) and analytics (Google Tag Manager)
- MariaDB via SQLAlchemy Core; schema migrations with Alembic; Docker-ready

## Quick start (local Python)

```bash
# Prerequisite: install uv — https://docs.astral.sh/uv/  (e.g. `brew install uv`)
# uv provisions Python 3.14 automatically; no system Python required.

make install              # uv sync + install git hooks
cp .env.example .env      # configure settings
docker compose up -d db   # start MariaDB
make migrate              # run database migrations
make web-createuser       # create a login user
make web-run              # web UI at http://localhost:8000
```

Also available: `make worker` (background job worker), `make seed` (demo data).

## Quick start (Docker Compose only)

No local Python needed — web and worker run in containers:

```bash
cp .env.example .env      # required: compose reads it via env_file
make compose-dev          # build + start db, web, worker (web with live reload)
make compose-migrate      # run database migrations
make compose-createuser   # create a login user
```

Open http://localhost:8000. Source edits under `backend/rentivo/` and `backend/legacy_web/` reload automatically; after editing job handlers run `docker compose restart worker`. Use `make compose-up` instead for an immutable (non-dev) stack.

See [docs/development.md](docs/development.md) for the full developer guide.

## Configuration

Copy `.env.example` to `.env`. All app variables use the `RENTIVO_` prefix. The most important ones:

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_DB_URL` | `...@localhost:3306/rentivo` | Database URL for host-side commands (compose containers are pinned to the `db` service automatically) |
| `RENTIVO_SECRET_KEY` | `change-me-in-production` | Session signing key — set a real value in production |
| `RENTIVO_STORAGE_BACKEND` | `local` | Invoice storage: `local` or `s3` |
| `RENTIVO_EMAIL_BACKEND` | `local` | `local` (writes `.eml` to `./outbox`) or `ses` |
| `RENTIVO_ENCRYPTION_BACKEND` | `base64` | PII encryption: `base64` (dev-only obfuscation) or `kms` |

**Full reference for all ~47 variables: [docs/configuration.md](docs/configuration.md)** — kept in sync with the code by a test.

## Makefile reference

<details>
<summary><strong>Local development</strong></summary>

| Command | Description |
|---------|-------------|
| `make install` | Sync dependencies into `.venv` with uv and install git hooks |
| `make web-run` | Start the web UI (uvicorn --reload, port 8000) |
| `make worker` | Run the background job worker |
| `make web-createuser` | Create a web login user |
| `make migrate` | Run pending Alembic migrations |
| `make migrate-fresh` | ⚠️ Drop all tables and re-migrate (dev only) |
| `make seed` | Seed the database with demo data |
| `make test` / `make test-cov` | Run tests (parallel) / with coverage |
| `make lint` / `make fmt` | Check / auto-fix lint and formatting |

</details>

<details>
<summary><strong>Maintenance scripts</strong></summary>

| Command | Description |
|---------|-------------|
| `make regenerate-pdfs` / `-dry` | Re-render all invoice PDFs |
| `make backfill-encryption` / `-dry` | Encrypt legacy plaintext rows (after enabling KMS) |
| `make backfill-encryption-reset-blind-index` | Rebuild email blind index after secret-key rotation |
| `make redact-audit-logs` / `-dry` | Redact PII from legacy audit log rows |

</details>

<details>
<summary><strong>Docker Compose</strong></summary>

| Command | Description |
|---------|-------------|
| `make compose-up` / `compose-down` | Start / stop the full stack (db, web, worker) |
| `make compose-dev` / `compose-dev-down` | Same, with source bind mounts + web live reload |
| `make compose-migrate` | Run migrations in the web container |
| `make compose-createuser` | Create a login user |
| `make compose-shell` | Bash in the web container |
| `make compose-logs` / `compose-logs-worker` | Tail logs |
| `make compose-regenerate` | Re-render PDFs inside the web container |

</details>

<details>
<summary><strong>Docker (standalone containers)</strong></summary>

| Command | Description |
|---------|-------------|
| `make build` / `up` / `down` / `restart` | Web image / container lifecycle |
| `make build-worker` / `up-worker` / `down-worker` | Worker image / container lifecycle |
| `make shell` / `shell-worker` | Bash in a container |
| `make docker-migrate` / `docker-createuser` | Migrations / user creation in the web container |
| `make logs` / `logs-worker` / `make health` | Logs / health check |

</details>

## Architecture

The repository is a uv workspace. Its Python backend is independently packaged under `backend/` and produces two deployables: the **legacy web app** (`backend/Dockerfile.legacy`) and the **job worker** (`backend/Dockerfile.worker`).

```
backend/
  pyproject.toml       # Python project and dependency metadata
  rentivo/
    settings.py        # Pydantic Settings (env prefix RENTIVO_)
    db.py              # SQLAlchemy engine; schema managed by Alembic
    models/            # Pydantic domain models (Billing, Bill, User, Organization, ...)
    repositories/      # Abstract bases + SQLAlchemy Core implementations
    services/          # Business logic (billing, bills, users, orgs, audit, email, ...)
    storage/           # Local / S3 invoice storage
    encryption/        # base64 / KMS field encryption + decryption cache
    cache/             # Generic key-value cache (memory / redis)
    jobs/              # Job queue: registry, worker loop, handlers (email, pdf, s3)
    workers/           # Worker entrypoint (run locally with make worker)
    pdf/               # fpdf2 invoice generator + pypdf receipt merger
    scripts/           # seed, regenerate_pdfs, backfill_encryption, redact_audit_logs
  legacy_web/
    app.py             # FastAPI app, middleware stack, templates
    auth.py            # Login / logout / signup / password recovery
    routes/            # Billing, bills, security (MFA/passkeys), organizations, invites
    templates/         # Jinja2 (PT-BR) + emails
    static/            # CSS + JS
  alembic/             # Migrations
```

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/configuration.md](docs/configuration.md) | Every environment variable, defaults, validation rules |
| [docs/development.md](docs/development.md) | Dev setup (local & compose-only), worker, migrations, troubleshooting |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Workflow, conventions, tests, PR expectations |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting |
| [CHANGELOG.md](CHANGELOG.md) | Release history (SemVer, Keep a Changelog) |

## Tech stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.14+ |
| Web framework | FastAPI + Uvicorn |
| Templates | Jinja2 + custom CSS |
| Database | MariaDB 11 (SQLAlchemy Core) |
| Migrations | Alembic |
| PDF generation | fpdf2 + pypdf |
| QR codes | qrcode (PIX) |
| Auth | bcrypt + session cookies, pyotp (TOTP), webauthn (passkeys) |
| Storage | Local filesystem / AWS S3 |
| Email | AWS SES / local .eml files |
| Encryption | AWS KMS (field-level PII) |
| Caching | cachetools / Redis (optional) |
| Logging | structlog |
| Containers | Docker + Docker Compose |
| CI/CD | GitHub Actions |
| Coverage | Codecov (100% threshold) |

## License

[GPL-3.0](LICENSE)
