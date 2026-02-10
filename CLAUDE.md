# Landlord

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
make landlord    # run CLI interactively
make shell-cli   # bash session

# Docker Compose (both services)
make compose-up            # start web + cli
make compose-down          # stop all
make compose-landlord      # run CLI in cli container
make compose-createuser    # create web user
```

## Architecture

- **Settings**: `landlord/settings.py` — Pydantic Settings, env prefix `LANDLORD_`, reads `.env`
- **Database**: `landlord/db.py` — SQLAlchemy engine + connection to MariaDB. Schema managed by Alembic. Configured via `LANDLORD_DB_URL`
- **Repositories**: `landlord/repositories/` — Abstract base classes in `base.py`, SQLAlchemy Core impl in `sqlalchemy.py`, factory in `factory.py`
- **Storage**: `landlord/storage/` — Same pattern. `LocalStorage` writes to `./invoices/`, `S3Storage` uploads to a private bucket with presigned URLs. Configurable via `LANDLORD_STORAGE_BACKEND`
- **PDF**: `landlord/pdf/invoice.py` — fpdf2-based invoice with navy/green color palette
- **Services**: `landlord/services/` — Business logic layer wiring repos + storage + PDF
- **CLI**: `landlord/cli/` — Interactive menus using `questionary` + `rich`
- **Health check**: `healthcheck.py` — HTTP server on port 2019, returns 200 for all requests

## S3 Storage

- S3 key pattern: `{billing_uuid}/{bill_uuid}.pdf`
- `pdf_path` column stores the S3 key, not a URL
- Presigned URLs (7-day expiry) are generated on the fly via `get_invoice_url()` / `get_presigned_url()`
- Set `LANDLORD_STORAGE_BACKEND=s3` and configure `LANDLORD_S3_*` env vars

## Conventions

- All customer-facing text (CLI prompts, PDF content) in **PT-BR**
- Currency in **BRL** (R$), formatted via `landlord.models.format_brl()`
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
- **Routes**: `web/routes/billing.py` and `web/routes/bill.py`
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
| `/login` | Login page |
| `/logout` | Logout |
| `/change-password` | Change password |

## Key Rules

- **NEVER delete `invoices/`** without explicit user confirmation
- Do not use floats for monetary values — always centavos (int)
- Keep repository and storage abstractions — they exist so backends can be swapped (S3, etc.)
