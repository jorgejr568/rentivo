# Development Guide

There are two supported ways to develop Rentivo. Both start with:

```bash
git clone https://github.com/jorgejr568/rentivo.git
cd rentivo
cp .env.example .env
```

## Path A — local Python + Docker for the database (recommended)

Prerequisite: [uv](https://docs.astral.sh/uv/) (`brew install uv`). uv provisions Python 3.14 automatically; no system Python needed.

```bash
make install              # uv sync --all-extras + install pre-commit hooks
docker compose up -d db   # MariaDB 11 on localhost:3306 (override with MYSQL_PORT)
make migrate              # run Alembic migrations
make seed                 # optional: demo data (billings, bills, users, orgs)
make web-createuser       # create a login user
make web-run              # http://localhost:8000 with auto-reload
```

Other entry points:

```bash
make worker               # background job worker (emails, PDF rendering)
```

## Path B — Docker Compose only (no local Python)

Everything runs in containers. `docker-compose.yml` pins the containers' DB host to the internal `db` service, so the `RENTIVO_DB_URL` in your `.env` (which points at `localhost` for Path A) does not need to change.

```bash
make compose-dev          # build + start db, web, worker — web has live reload
make compose-migrate      # run migrations inside the web container
make compose-createuser   # create a login user
open http://localhost:8000
```

`make compose-dev` layers `docker-compose.dev.yml` on top of the base file: it bind-mounts `./backend/rentivo` and `./backend/legacy_web` into the containers and runs uvicorn with `--reload`, so web/code changes apply without rebuilding. Two caveats:

- The **worker** has no auto-reload — after editing job handlers run `docker compose restart worker`.

Plain `make compose-up` starts the same stack without bind mounts (code baked into images — for *running*, not developing).

Seeding demo data is host-side only (the images don't ship `faker`): with Path A tooling installed, `make seed` works against the compose DB because `.env` points at `localhost:3306`.

## React/frontend development

The replacement frontend requires Node.js 22 and npm. It remains a preview and does not change the default legacy development or production commands.

```bash
make frontend-install        # npm ci from frontend/package-lock.json
make frontend-dev            # Vite development server
make frontend-build          # typecheck + production bundle
make frontend-test-cov       # Vitest with 100% coverage thresholds
```

FastAPI owns the OpenAPI contract. When an API route or schema changes, refresh both committed artifacts, then verify that regeneration is clean:

```bash
make openapi-export          # write frontend/openapi.json from FastAPI
make openapi-generate        # regenerate TypeScript API types
make openapi-check           # non-mutating freshness check used by CI
```

## End-to-end and visual parity

Playwright exercises the replacement preview and compares deterministic desktop/mobile captures with the reviewed baselines:

```bash
make e2e                    # E2E, accessibility, and visual-parity checks
make e2e-update             # update baselines after reviewing an intentional change
```

Treat baseline updates as UI changes: inspect the images and include the evidence in the pull request.

## Replacement preview

The dedicated `preview-*` targets use `docker-compose.next.yml`; they do not alter the default production or legacy Compose files. Prepare `.env.preview-db` and `.env.preview-app` as described in the [preview runbook](runbooks/frontend-backend-preview.md), then:

```bash
make preview-config          # validate merged local Compose configuration
make preview-build           # build legacy, worker, API, and frontend images
make preview-up              # migrate and start the preview at localhost:8080
make preview-stop            # stop proxy, frontend, and API only
```

Remote validation uses the same secret-managed environment paths and exported routing values documented in the runbook:

```bash
make preview-config-remote \
  RENTIVO_DB_ENV_FILE=/etc/rentivo/preview-db.env \
  RENTIVO_APP_ENV_FILE=/etc/rentivo/preview-app.env
```

The detailed environment split, parity fixture seeding, TLS setup, health checks, and rollback procedure live only in the [frontend/backend preview runbook](runbooks/frontend-backend-preview.md).

## Tests, lint, hooks

```bash
make test                 # pytest -n auto (always parallel)
make test-cov             # with coverage report
make lint                 # ruff check + format check
make fmt                  # auto-format
```

- **Coverage is enforced at 100%** (`fail_under = 100` in `backend/pyproject.toml`). Every new line must be tested or carry `# pragma: no cover` with a good reason.
- Tests use in-memory SQLite; no database or network needed.
- `make install` registers pre-commit hooks that run ruff check, ruff format, and the **full test suite** on every commit. Bypass in an emergency with `git commit -n` (CI will still enforce everything).

## Background worker & jobs

State-changing web flows enqueue rows into the `jobs` table; the worker (`make worker` locally, `backend/Dockerfile.worker` in production) polls and dispatches registered handlers:

| Job type | Handler | Purpose |
|----------|---------|---------|
| `email.send` | `backend/rentivo/jobs/handlers/email.py` | Transactional emails via the configured email backend |
| `communication.send` | `backend/rentivo/jobs/handlers/communication.py` | Send a tenant communication email with the bill PDF attached |
| `pdf.render` | `backend/rentivo/jobs/handlers/pdf.py` | Render a bill's invoice PDF in the background |
| `s3.delete` | `backend/rentivo/jobs/handlers/s3.py` | Deferred deletion of storage objects |

Tuning knobs: `RENTIVO_JOB_WORKER_*` (see [configuration.md](configuration.md)). New handlers register themselves via `@register("job.type")` in `backend/rentivo/jobs/handlers/` — the worker entrypoint needs no changes.

Job drivers (database vs Temporal) are documented in [`jobs.md`](jobs.md).

With `RENTIVO_EMAIL_BACKEND=local`, sent emails are `.eml` files in `./outbox` (host) or `/app/outbox` inside the worker container (`docker compose exec worker ls outbox`).

## Tracing (optional)

Distributed tracing is off by default. To try it locally: `uv sync --extra otel`, `make jaeger-up`, set `RENTIVO_OTEL_ENABLED=true` in `.env`, then open http://localhost:16686. Full guide: [`docs/observability.md`](observability.md).

## Database migrations

Schema is managed by Alembic (`backend/alembic/versions/`).

```bash
make migrate              # upgrade to head
make migrate-fresh        # DROP ALL TABLES and re-migrate — destructive, dev only
uv run --project backend alembic -c backend/alembic.ini revision -m "add foo column"   # new migration
```

Never invent revision IDs by hand — always let `alembic revision` generate them.

## Maintenance scripts

| Command | Purpose |
|---------|---------|
| `make seed` | Demo data for local development (idempotent-ish; safe to re-run on a dev DB) |
| `make regenerate-pdfs` / `-dry` | Re-render every invoice PDF |
| `make backfill-encryption` / `-dry` | Encrypt legacy plaintext rows after enabling KMS |
| `make backfill-encryption-reset-blind-index` | Rebuild `users.email_hash` after rotating `RENTIVO_SECRET_KEY` |
| `make redact-audit-logs` / `-dry` | Redact PII from legacy audit_log rows |

## Troubleshooting

- **Port 3306 already in use** — set `MYSQL_PORT=3307` in `.env` and update the port in `RENTIVO_DB_URL` to match.
- **Web container crashes with "Can't connect to MySQL server on 'localhost'"** — you are overriding `RENTIVO_DB_URL` in the container environment; inside compose the host must be `db` (the base compose file handles this — don't fight it).
- **Sessions reset on every restart / warning `secret_key_not_configured`** — set a real `RENTIVO_SECRET_KEY`.
- **`db` service unhealthy on first boot** — MariaDB initializes its datadir on first run; give it ~15s, the app containers wait via `depends_on: service_healthy`.
- **Worker restarts a few times on first compose boot** — it needs the `jobs` table, which only exists after `make compose-migrate`; the `restart: unless-stopped` policy retries until then. Harmless once migrations have run.
- **Stale DB schema after switching branches** — `make migrate-fresh` (drops everything) then `make seed`.
