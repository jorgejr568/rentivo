<h1 align="center">Rentivo</h1>

<p align="center">
  Apartment billing management with PDF invoice generation — <strong>CLI + Web UI</strong>
</p>

<p align="center">
  <a href="https://github.com/jorgejr568/rentivo/actions/workflows/deploy.yml"><img src="https://github.com/jorgejr568/rentivo/actions/workflows/deploy.yml/badge.svg" alt="Tests"></a>
  <a href="https://codecov.io/gh/jorgejr568/rentivo"><img src="https://codecov.io/gh/jorgejr568/rentivo/branch/main/graph/badge.svg" alt="codecov"></a>
  <a href="https://github.com/jorgejr568/rentivo/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue" alt="GPL-3.0"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/MariaDB-11-003545?logo=mariadb&logoColor=white" alt="MariaDB">
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/SQLAlchemy-Core-D71F00?logo=sqlalchemy&logoColor=white" alt="SQLAlchemy">
</p>

---

Built for Brazilian rentivos — all tenant-facing output is in **PT-BR** with **BRL (R$)** currency and **PIX QR codes** on invoices.

## Features

- Create and manage recurring billing templates with multiple line items
- Generate professional PDF invoices with PIX QR codes for easy payment
- **Web UI** (FastAPI) for browser-based management, or **interactive CLI**
- User management with bcrypt password hashing
- Attach receipt files (PDF, JPG, PNG) to bills — merged into the invoice PDF
- Comprehensive audit logging of all operations (create, update, delete, login, etc.)
- Store invoices locally or on S3 with presigned URLs
- MariaDB as the database backend (via SQLAlchemy)
- Schema migrations with Alembic
- Docker-ready with health check endpoint

## Quick Start

```bash
make install              # create venv + install deps
cp .env.example .env      # configure settings
docker compose up -d db   # start MariaDB
make migrate              # run database migrations
make run                  # start the interactive CLI
```

### Web UI

```bash
docker compose up -d db   # start MariaDB (if not running)
make migrate              # run database migrations (first time)
make web-createuser       # create a login user
make web-run              # start web UI at http://localhost:8000
```

### Docker Compose

```bash
make compose-up           # start MariaDB + web + CLI
make compose-createuser   # create a login user
```

## Configuration

Copy `.env.example` to `.env`. All variables use the `RENTIVO_` prefix.

<details>
<summary><strong>Database</strong></summary>

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_DB_URL` | `mysql://rentivo:rentivo@db:3306/rentivo` | SQLAlchemy database URL (MariaDB) |

</details>

<details>
<summary><strong>Storage</strong></summary>

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_STORAGE_BACKEND` | `local` | `local` or `s3` |
| `RENTIVO_STORAGE_LOCAL_PATH` | `./invoices` | Local directory for PDFs |
| `RENTIVO_S3_BUCKET` | | S3 bucket name |
| `RENTIVO_S3_REGION` | | AWS region |
| `RENTIVO_S3_ACCESS_KEY_ID` | | AWS access key |
| `RENTIVO_S3_SECRET_ACCESS_KEY` | | AWS secret key |
| `RENTIVO_S3_ENDPOINT_URL` | | Custom S3 endpoint (MinIO, etc.) |
| `RENTIVO_S3_PRESIGNED_EXPIRY` | `604800` | Presigned URL expiry in seconds (default 7 days) |

</details>

<details>
<summary><strong>PIX</strong></summary>

| Variable | Description |
|----------|-------------|
| `RENTIVO_PIX_KEY` | PIX key (CPF, email, phone, or random) |
| `RENTIVO_PIX_MERCHANT_NAME` | Merchant name for QR code |
| `RENTIVO_PIX_MERCHANT_CITY` | Merchant city for QR code |

</details>

<details>
<summary><strong>Web</strong></summary>

| Variable | Default | Description |
|----------|---------|-------------|
| `RENTIVO_SECRET_KEY` | `change-me-in-production` | Secret key for session signing |

</details>

## Makefile Reference

<details>
<summary><strong>Local</strong></summary>

| Command | Description |
|---------|-------------|
| `make install` | Create virtualenv and install dependencies |
| `make run` | Run the CLI |
| `make migrate` | Run pending Alembic migrations |
| `make web-run` | Start the web UI (uvicorn, port 8000) |
| `make web-createuser` | Create a web login user |
| `make test` | Run tests |
| `make test-cov` | Run tests with coverage report |
| `make regenerate-pdfs` | Regenerate all invoice PDFs |
| `make regenerate-pdfs-dry` | Preview regeneration (dry run) |

</details>

<details>
<summary><strong>Docker (Web)</strong></summary>

| Command | Description |
|---------|-------------|
| `make build` | Build the web Docker image |
| `make up` / `make down` | Start / stop the web container |
| `make docker-createuser` | Create a login user in the container |
| `make shell` | Open a bash shell in the container |
| `make docker-migrate` | Run migrations in the container |
| `make logs` | Tail container logs |
| `make health` | Check the health endpoint |

</details>

<details>
<summary><strong>Docker (CLI)</strong></summary>

| Command | Description |
|---------|-------------|
| `make build-cli` | Build the CLI Docker image |
| `make up-cli` / `make down-cli` | Start / stop the CLI container |
| `make rentivo` | Run the CLI in the container |
| `make shell-cli` | Open a bash shell in the CLI container |

</details>

<details>
<summary><strong>Docker Compose</strong></summary>

| Command | Description |
|---------|-------------|
| `make compose-up` / `compose-down` | Start / stop with Compose |
| `make compose-rentivo` | Run the CLI via Compose |
| `make compose-createuser` | Create a login user via Compose |
| `make compose-migrate` | Run migrations via Compose |

</details>

## Architecture

```
rentivo/
  settings.py          # Pydantic Settings (env prefix RENTIVO_)
  db.py                # SQLAlchemy engine + connection
  models/              # Pydantic models (Billing, Bill, User)
  repositories/        # Abstract base + SQLAlchemy Core implementation
  services/            # Business logic (billing, bill, user services)
  storage/             # Abstract base + Local / S3 implementations
  pdf/                 # fpdf2 invoice generator + pypdf receipt merger
  cli/                 # Interactive menus (questionary + rich)
  scripts/             # Maintenance scripts (PDF regeneration)
web/
  app.py               # FastAPI app, middleware, templates
  auth.py              # Login, logout, change password routes
  deps.py              # Auth middleware, service factories
  routes/              # Billing + bill CRUD routes
  templates/           # Jinja2 templates
  static/              # CSS + JS
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.10+ |
| Web Framework | FastAPI + Uvicorn |
| Templates | Jinja2 + custom CSS |
| Database | MariaDB 11 (SQLAlchemy Core) |
| Migrations | Alembic |
| PDF Generation | fpdf2 + pypdf |
| QR Codes | qrcode (PIX) |
| Auth | bcrypt + session cookies |
| Storage | Local filesystem / AWS S3 |
| CLI | questionary + rich |
| Containers | Docker + Docker Compose |
| CI/CD | GitHub Actions |
| Coverage | Codecov (95%+ threshold) |

## License

[GPL-3.0](LICENSE)
