<h1 align="center">Rentivo</h1>

<p align="center">
  Apartment billing management with PDF invoice generation
</p>

<p align="center">
  <a href="https://github.com/jorgejr568/rentivo/actions/workflows/deploy.yml"><img src="https://github.com/jorgejr568/rentivo/actions/workflows/deploy.yml/badge.svg" alt="CI"></a>
  <a href="https://codecov.io/gh/jorgejr568/rentivo"><img src="https://codecov.io/gh/jorgejr568/rentivo/branch/main/graph/badge.svg" alt="codecov"></a>
  <a href="https://github.com/jorgejr568/rentivo/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue" alt="GPL-3.0"></a>
</p>

Built for Brazilian landlords: tenant-facing output is in **PT-BR**, with
**BRL (R$)** currency and PIX QR codes on invoices.

## Features

- Recurring billing templates and one-click monthly bill generation
- PDF invoices, PIX QR codes, receipt attachments, and payment receipts
- React/Vite browser application backed by the versioned FastAPI API
- API-key authentication with scopes and per-organization grants
- One-day hidden login keys for browser sessions, revoked on logout
- TOTP MFA, passkeys (WebAuthn), Google login, and password recovery
- Organizations with owner/admin/manager/viewer roles and email invites
- Background jobs for email, PDF rendering, exports, and storage cleanup
- KMS field encryption, audit logging with PII redaction, S3, and SES
- MariaDB, Alembic migrations, Nginx edge proxy, and optional Temporal/OTel

## Production topology

The default Compose manifest is the production service topology:

```text
MariaDB -> one-shot Alembic migration -> FastAPI API + worker
                                      -> React static frontend
                                      -> Nginx edge proxy
```

Nginx exposes the application on `127.0.0.1:8080` by default. It sends
`/api/v1` and public machine endpoints to FastAPI and browser routes to React.
API and worker start only after migration succeeds; Nginx waits for API
readiness and frontend health.

## Local development

Prerequisites: [uv](https://docs.astral.sh/uv/), Node.js 22+, npm, Docker, and
Docker Compose.

```bash
git clone https://github.com/jorgejr568/rentivo.git
cd rentivo
cp .env.example .env
cp .env.db.example .env.db
make install
make compose-dev
```

Open <http://localhost:8080>. The development override uses the same services
as production, bind-mounts backend and frontend source, enables Uvicorn/Vite
reload, and uses `.env.db` for local MariaDB provisioning. Restart the
worker after changing handlers because it does not auto-reload:

```bash
RENTIVO_APP_ENV_FILE=.env docker compose --env-file .env.db \
  -f docker-compose.yml -f docker-compose.dev.yml restart worker
```

For split-process development, start MariaDB with the split-env Compose command
in the development guide, run `make migrate`, then run `make frontend-dev`, the
FastAPI Uvicorn entrypoint, and `make worker` in separate terminals. See the
[development guide](docs/development.md) for exact commands.

## Production configuration

Production uses separate database interpolation and application environment
files. Start from `.env.db.example` and `.env.example`, then store real values in
the deployment secret manager. `make stack-config` validates the source Compose
topology against those files; it does not deploy production.

Override the secret-managed file locations when needed:

```bash
make stack-config \
  RENTIVO_DB_ENV_FILE=/etc/rentivo/db.env \
  RENTIVO_APP_ENV_FILE=/etc/rentivo/app.env
```

Follow the [production release runbook](docs/runbooks/production-release.md)
for the only supported deployment path: protected automation consuming the
complete-gate-tested immutable SHA and image digests. Local `stack-build` and
`stack-up` outputs are never production release artifacts.

## Development and verification commands

| Command | Purpose |
|---|---|
| `make frontend-install` | Install locked frontend dependencies |
| `make frontend-dev` / `frontend-build` | Run Vite / build the production bundle |
| `make frontend-test-cov` | Run Vitest with 100% coverage thresholds |
| `make worker` | Run the configured background-job worker locally |
| `make migrate` | Upgrade a host-connected database to Alembic head |
| `make seed` | Seed local demonstration data |
| `make lint` / `fmt` | Check / fix Python formatting and lint |
| `make test` / `test-cov` | Run backend tests / explicit coverage report |
| `make openapi-export` / `openapi-generate` | Refresh API snapshot / generated types |
| `make openapi-check` | Verify committed OpenAPI artifacts are current |
| `make e2e` / `e2e-update` | Run Playwright / update reviewed baselines |
| `make jaeger-up` / `jaeger-down` | Start / stop the observability profile |
| `make temporal-up` / `temporal-down` | Start / stop the Temporal profile |

## Configuration

All application variables use the `RENTIVO_` prefix. Copy `.env.example` for
local development and copy `.env.db.example` to `.env.db` for Compose database
provisioning. Production injects both files from its secret manager.

| Variable | Development default | Purpose |
|---|---|---|
| `RENTIVO_DB_URL` | MariaDB on `localhost:3306` | SQLAlchemy database URL |
| `RENTIVO_SECRET_KEY` | development placeholder | API-key hashing/session secret |
| `RENTIVO_PUBLIC_URL` | request-derived | Canonical public origin |
| `RENTIVO_STORAGE_BACKEND` | `local` | `local` or `s3` invoice storage |
| `RENTIVO_EMAIL_BACKEND` | `local` | local `.eml` or AWS SES |
| `RENTIVO_ENCRYPTION_BACKEND` | `base64` | development obfuscation or AWS KMS |
| `RENTIVO_JOB_BACKEND` | `database` | database polling or Temporal |

Production validation rejects development secrets, insecure cookies, localhost
origins, local storage/email, and reversible encryption. See the generated
[configuration reference](docs/configuration.md) for every setting.

## Architecture

The repository is a uv workspace with independently packaged backend and
frontend applications.

```text
backend/
  rentivo/
    api/              FastAPI app, middleware, routes, and schemas
    models/           Pydantic domain models
    repositories/     Abstract contracts and SQLAlchemy Core implementations
    services/         Billing, bills, users, organizations, auth, and audit
    jobs/             Database and Temporal drivers, registry, and handlers
    workers/          Worker entrypoint
    email/            Transactional templates and rendering
    storage/          Local and S3 invoice storage
    encryption/       Base64/KMS field encryption and caches
    observability/    Structured logging and OpenTelemetry tracing
    pdf/              Invoice and receipt PDF generation
    scripts/          Maintenance and data migration commands
  alembic/            Schema migrations
frontend/
  src/                React/Vite/TypeScript application
  e2e/                Playwright workflows and reviewed visual baselines
infra/proxy/           Nginx edge configuration
```

## Documentation

| Document | Contents |
|---|---|
| [Configuration](docs/configuration.md) | Environment variables and validation rules |
| [Development](docs/development.md) | Local and Compose development workflows |
| [Job drivers](docs/jobs.md) | Database and optional Temporal job execution |
| [Observability](docs/observability.md) | Logging, traces, profiles, and production signals |
| [Production release](docs/runbooks/production-release.md) | Big-bang deployment and recovery runbook |
| [Contributing](CONTRIBUTING.md) | Workflow, conventions, tests, and PR expectations |
| [Security](SECURITY.md) | Private vulnerability reporting |
| [Changelog](CHANGELOG.md) | SemVer release history |

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, TypeScript |
| Backend API | FastAPI, Uvicorn |
| Database | MariaDB 11, SQLAlchemy Core |
| Migrations | Alembic |
| Edge | Nginx |
| Jobs | Database worker or optional Temporal |
| Auth | API keys, secure cookies, TOTP, WebAuthn |
| Storage / email | Local or S3 / local or SES |
| Encryption | AWS KMS in production |
| Observability | structlog, OpenTelemetry, Jaeger/CloudWatch |
| CI/CD | GitHub Actions |

## License

[GPL-3.0](LICENSE)
