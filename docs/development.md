# Development Guide

Rentivo is a React/Vite application backed by FastAPI, a background worker, and
MariaDB. Nginx is the single browser entrypoint in the default Compose topology.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (provisions Python 3.14)
- Node.js 22+ and npm
- Docker and Docker Compose

```bash
git clone https://github.com/jorgejr568/rentivo.git
cd rentivo
cp .env.example .env
cp .env.db.example .env.db
make install
```

## Compose development (recommended)

The development override layers `docker-compose.dev.yml` onto the production
service topology. It uses `.env.db` for local MariaDB values,
bind-mounts `backend/rentivo` and `frontend`, and enables Uvicorn and Vite
reload.

```bash
make compose-dev
open http://localhost:8080
```

Services are `db`, one-shot `migrate`, `api`, `worker`, `frontend`, and `proxy`.
The proxy listens on `127.0.0.1:8080`; MariaDB listens on `127.0.0.1:3306`.
The frontend and API are internal to Compose.

Backend and frontend edits reload automatically. The worker does not reload;
restart it after changing jobs or shared backend code:

```bash
RENTIVO_APP_ENV_FILE=.env docker compose --env-file .env.db \
  -f docker-compose.yml -f docker-compose.dev.yml restart worker
```

Useful commands:

```bash
make compose-logs           # follow all services
make compose-logs-worker    # follow worker only
make compose-shell          # shell in the API container
make compose-createuser     # create a login user
make compose-dev-down       # stop the development stack
```

All `compose-*` development helpers use this same `.env` plus `.env.db` contract
and the development override. Override `RENTIVO_DEV_DB_ENV_FILE` or
`RENTIVO_APP_ENV_FILE` when testing alternate local files.

## Split-process development

Run MariaDB in Compose and the applications on the host when debugging Python
or frontend tooling directly:

```bash
RENTIVO_APP_ENV_FILE=.env docker compose --env-file .env.db \
  -f docker-compose.yml -f docker-compose.dev.yml up -d db
make migrate
make frontend-install
```

Run these in separate terminals:

```bash
uv run --project backend uvicorn rentivo.api.app:create_app \
  --factory --reload --host 127.0.0.1 --port 8001
make frontend-dev
make worker
```

Open <http://localhost:5173>. Vite proxies `/api/v1` to
`http://127.0.0.1:8001`. Keep `.env` development origins/cookies aligned with
the address used in the browser. `make seed` adds optional demonstration data.

## Frontend and API contract

```bash
make frontend-install        # npm ci from the lockfile
make frontend-dev            # Vite development server
make frontend-build          # typecheck and production bundle
make frontend-test-cov       # Vitest with 100% coverage
```

FastAPI owns the OpenAPI contract. Refresh both committed artifacts after an
API route or schema change:

```bash
make openapi-export          # write frontend/openapi.json
make openapi-generate        # regenerate TypeScript API types
make openapi-check           # non-mutating CI freshness check
```

Do not hand-edit generated OpenAPI types.

## End-to-end and visual tests

```bash
make e2e                    # Playwright workflows, a11y, and visual checks
make e2e-update             # update reviewed visual baselines
```

The normal suite uses deterministic fixtures for fast workflow coverage. The
production-stack project, selected by `PLAYWRIGHT_PRODUCTION_STACK=1`, runs
without request interception against the MariaDB-backed Compose topology.
Treat snapshot changes as product changes: inspect desktop and mobile images
before committing them.

## Tests, lint, and hooks

```bash
make lint
make test
make test-cov
npm --prefix frontend run lint
npm --prefix frontend run typecheck
make frontend-test-cov
make openapi-check
```

Backend and authored frontend code enforce 100% coverage. Backend tests run in
parallel and normally use isolated SQLite databases. `make install` registers
pre-commit hooks for formatting, lint, and the full test suite.

## Jobs and worker

State-changing API flows enqueue background jobs for email, communications,
PDF/receipt rendering, exports, and storage cleanup. Run the worker with
`make worker` on the host or as the Compose `worker` service. New database-driver
handlers register through `@register("job.type")` in
`backend/rentivo/jobs/handlers/`.

The database driver is the production default. Temporal is optional and uses
the same worker entrypoint. Driver behavior and extension steps are documented
in [jobs.md](jobs.md).

With `RENTIVO_EMAIL_BACKEND=local`, sent messages are `.eml` files in
`./outbox` on the host or `/app/outbox` in the worker container.

## Optional profiles

OpenTelemetry is disabled by default. Start local Jaeger and enable tracing:

```bash
make jaeger-up
# .env when using Compose:
# RENTIVO_OTEL_ENABLED=true
# RENTIVO_OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
```

Jaeger is at <http://localhost:16686>. Stop it with `make jaeger-down`.

Start the optional local Temporal cluster and UI:

```bash
make temporal-up
# Temporal: localhost:7233; UI: http://localhost:8233
make temporal-down
```

Inside Compose, use `RENTIVO_TEMPORAL_HOST=temporal:7233`; host processes use
`localhost:7233`. See [observability.md](observability.md) and
[jobs.md](jobs.md).

## Database migrations

Schema is managed by Alembic in `backend/alembic/versions/`.

```bash
make migrate
uv run --project backend alembic -c backend/alembic.ini heads
uv run --project backend alembic -c backend/alembic.ini revision -m "add foo"
```

`make migrate-fresh` and `make compose-migrate-fresh` drop all tables. Use them
only against disposable development databases. Let Alembic generate revision
IDs; never invent them by hand.

## Disposable production-topology rehearsal

Use production-equivalent disposable values in separate application and
database files to test source topology and startup ordering locally:

```bash
make stack-config \
  RENTIVO_DB_ENV_FILE=/path/to/db.env \
  RENTIVO_APP_ENV_FILE=/path/to/app.env
make stack-build \
  RENTIVO_DB_ENV_FILE=/path/to/db.env \
  RENTIVO_APP_ENV_FILE=/path/to/app.env
make stack-up \
  RENTIVO_DB_ENV_FILE=/path/to/db.env \
  RENTIVO_APP_ENV_FILE=/path/to/app.env
```

`stack-up` runs the migration service before API and worker and exposes Nginx
on `RENTIVO_PORT` (default `8080`). Use `make stack-migrate` only for an explicit
migration-only rehearsal. These targets build local images and are not a
production deployment mechanism. Production releases and previous-version
redeploys use only protected automation with complete-gate-tested immutable
image digests; follow the
[production release runbook](runbooks/production-release.md).

## Maintenance scripts

| Command | Purpose |
|---|---|
| `make seed` | Add demonstration data to a development database |
| `make regenerate-pdfs` / `-dry` | Re-render invoice PDFs |
| `make regenerate-recibos` / `-dry` | Enqueue paid-bill receipt rendering |
| `make backfill-encryption` / `-dry` | Encrypt historical plaintext rows after enabling KMS |
| `make backfill-encryption-reset-blind-index` | Rebuild the user email blind index after key rotation |
| `make redact-audit-logs` / `-dry` | Redact historical audit-log PII |

## Troubleshooting

- **Port 3306 is busy:** override `MYSQL_PORT` and keep host-side
  `RENTIVO_DB_URL` aligned.
- **Port 8080 is busy:** set `RENTIVO_PORT` for the Compose proxy.
- **Container tries `localhost` for MariaDB:** use the default Compose
  environment; containers must connect to host `db`.
- **Production configuration is rejected:** production intentionally rejects
  development secrets, HTTP/localhost origins, insecure cookies, local
  email/storage, and base64 encryption.
- **Worker code seems stale:** restart the `worker` service; it has no reload.
- **Schema is stale after changing branches:** run `make migrate`, or rebuild a
  disposable development database with `make migrate-fresh`.
