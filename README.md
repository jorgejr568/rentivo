# Billing Generator

Apartment billing management CLI app with PDF invoice generation.

## Quick Start

### Local

```bash
make install       # create venv and install deps
cp .env.example .env  # configure your settings
make migrate       # run database migrations
make run           # start the interactive CLI
```

### Docker

```bash
make build         # build the image
make up            # start container (reads .env, exposes port 2019)
make billing       # run the billing CLI inside the container
make shell         # open a bash shell in the container
```

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make install` | Create virtualenv and install dependencies |
| `make run` | Run the billing CLI locally |
| `make migrate` | Run pending Alembic migrations locally |
| `make regenerate-pdfs` | Regenerate all invoice PDFs |
| `make regenerate-pdfs-dry` | Preview regeneration (no changes) |
| `make build` | Build the Docker image |
| `make up` | Start the container |
| `make down` | Stop and remove the container |
| `make restart` | Restart the container |
| `make shell` | Open bash in the running container |
| `make billing` | Run the billing CLI in the container |
| `make docker-migrate` | Run migrations in the container |
| `make docker-regenerate` | Regenerate PDFs in the container |
| `make logs` | Tail container logs |
| `make health` | Check the health endpoint |

## Configuration

Copy `.env.example` to `.env` and fill in the values. All variables use the `BILLING_` prefix.

### Storage Backends

- **Local** (default): PDFs saved to `./invoices/`
- **S3**: Set `BILLING_STORAGE_BACKEND=s3` and configure the `BILLING_S3_*` variables. Invoices are uploaded to a private S3 bucket and accessed via presigned URLs (7-day expiry).

### S3 Key Pattern

Invoices are stored as `{billing_uuid}/{bill_uuid}.pdf`. The `pdf_path` column stores the S3 key; presigned URLs are generated on the fly.

## Architecture

- **Settings**: `billing/settings.py` — Pydantic Settings, env prefix `BILLING_`, reads `.env`
- **Database**: `billing/db.py` — SQLite via `sqlite3` stdlib. Schema managed by Alembic. Configurable backend via `BILLING_DB_BACKEND`
- **Repositories**: `billing/repositories/` — Abstract base classes in `base.py`, SQLite impl in `sqlite.py`, factory in `factory.py`. Add new backends by implementing the ABCs
- **Storage**: `billing/storage/` — Same pattern. `LocalStorage` writes to `./invoices/`, `S3Storage` uploads to S3. Configurable via `BILLING_STORAGE_BACKEND`
- **PDF**: `billing/pdf/invoice.py` — fpdf2-based invoice with navy/green color palette
- **Services**: `billing/services/` — Business logic layer wiring repos + storage + PDF
- **CLI**: `billing/cli/` — Interactive menus using `questionary` + `rich`

## Conventions

- All customer-facing text (CLI prompts, PDF content) in **PT-BR**
- Currency in **BRL** (R$), formatted via `billing.models.format_brl()`
- Money stored as **centavos (int)** in the database — never use floats for money
- Code (variable names, comments) in English
