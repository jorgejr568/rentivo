# Frontend-Backend Preview Runbook

This preview runs the React frontend and FastAPI API beside the legacy application. It is for local development and
staging validation only. The default `docker-compose.yml` and production deployment continue to target the legacy app.

## Prerequisites

- Docker Engine with Docker Compose v2.
- An application-only environment file, such as `.env.preview-app`, with a non-default `RENTIVO_SECRET_KEY` and an
  independently URL-encoded `RENTIVO_DB_URL`.
- A separate Compose interpolation file, such as `.env.preview-db`, containing only the four MariaDB values.
- `uv` and the locked backend environment when generating parity credentials on the host.
- For remote preview, a TLS terminator and a secret-managed environment file outside the repository.

Never commit either environment file, parity credentials, database passwords, cloud credentials, or TLS private keys. Do
not put `MYSQL_ROOT_PASSWORD` or the other Compose-only database variables in the application environment file. The seeder
refuses `RENTIVO_ENVIRONMENT=production`; it accepts only `dev` and `staging`.

## Required Environment

The full application reference is in [Configuration](../configuration.md). These values are specific to the preview:

| Variable | Local preview | Remote preview |
| --- | --- | --- |
| `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD` | Development-only values | Unique values from the staging secret store |
| `RENTIVO_DB_URL` | Required in the application file; URL-encode credentials | Required application DSN from the staging secret store |
| `RENTIVO_APP_ENV_FILE` | Path to the application-only file; defaults to optional `.env.preview-app` | Required path to the application-only file |
| `RENTIVO_SECRET_KEY` | A stable local value | A strong value from the staging secret store |
| `RENTIVO_PREVIEW_ORIGIN` | Optional; defaults to `http://localhost:8080` | Required exact public origin, such as `https://preview.example.com`, with no path or trailing slash |
| `RENTIVO_WEBAUTHN_RP_ID` | Fixed by Compose to `localhost` | Required hostname only, such as `preview.example.com` |
| `RENTIVO_TRUSTED_TLS_TERMINATOR_CIDR` | Defaults to loopback | Required exact address or narrow CIDR of the TLS terminator |
| `RENTIVO_PREVIEW_PORT` | Optional; defaults to `8080` on loopback | Required loopback port used only by the co-located TLS terminator |
| `RENTIVO_PARITY_PASSWORD` | Required only while seeding | Required only while seeding; obtain from the staging secret store |
| `RENTIVO_PARITY_TOTP_SECRET` | Required uppercase base32 of at least 32 characters while seeding | Required uppercase base32 of at least 32 characters while seeding; obtain from the staging secret store |

Choose storage, email, encryption, cache, and observability settings as described in the configuration reference. Remote
preview should use staging-grade backends and credentials rather than the local defaults.

## Local Preview

Generate disposable parity credentials in the current shell. These commands do not write them to the repository:

```bash
export RENTIVO_PARITY_PASSWORD="$(openssl rand -hex 20)"
export RENTIVO_PARITY_TOTP_SECRET="$(uv run --project backend python -c 'import pyotp; print(pyotp.random_base32())')"
```

Create the two ignored files with strict permissions. The database file contains only `MYSQL_DATABASE`, `MYSQL_USER`,
`MYSQL_PASSWORD`, and `MYSQL_ROOT_PASSWORD`; the application file contains Rentivo settings and no `MYSQL_*` values.
Set `RENTIVO_DB_URL` in the application file to a SQLAlchemy URL such as
`mysql+pymysql://rentivo:encoded-password@db:3306/rentivo`. Percent-encode the username, password, and database name;
do not copy raw values containing `@`, `:`, `/`, `%`, `?`, or `#` into the URL. Keeping this DSN separate from Compose
interpolation prevents raw database credentials from being parsed as URL syntax.
Then build the images, start MariaDB, apply migrations, seed the two dedicated accounts, and start the stack:

```bash
export RENTIVO_DB_ENV_FILE=.env.preview-db
export RENTIVO_APP_ENV_FILE=.env.preview-app
chmod 600 "$RENTIVO_DB_ENV_FILE" "$RENTIVO_APP_ENV_FILE"
docker compose --env-file "$RENTIVO_DB_ENV_FILE" -f docker-compose.next.yml build rentivo worker api frontend
docker compose --env-file "$RENTIVO_DB_ENV_FILE" -f docker-compose.next.yml up -d db
docker compose --env-file "$RENTIVO_DB_ENV_FILE" -f docker-compose.next.yml \
  run --rm api alembic -c backend/alembic.ini upgrade head
docker compose --env-file "$RENTIVO_DB_ENV_FILE" -f docker-compose.next.yml run --rm \
  -e RENTIVO_PARITY_PASSWORD -e RENTIVO_PARITY_TOTP_SECRET \
  api python scripts/seed_parity_fixtures.py
docker compose --env-file "$RENTIVO_DB_ENV_FILE" -f docker-compose.next.yml \
  up -d rentivo worker api frontend proxy
```

Open the replacement preview at `http://localhost:8080`. The legacy app remains available at
`http://localhost:8000`. Both parity accounts use `RENTIVO_PARITY_PASSWORD`:

- `parity.user@example.com` has no MFA and is suitable for setup flows.
- `parity.mfa@example.com` has confirmed TOTP using `RENTIVO_PARITY_TOTP_SECRET`.

The database, legacy app, and replacement proxy are all published on host loopback only. The frontend listens on port
`8080` inside its container as an unprivileged user; browser traffic reaches it through the proxy. The seeder deletes and
recreates only the two dedicated accounts. If creation fails partway through, it removes both fixture accounts so the next
run starts from a deterministic empty fixture state. Re-running it resets their password and authentication
rows covered by user-deletion cascades, including login tokens, passkeys, TOTP, and recovery codes. Do not use those
addresses for non-fixture data. If a fixture account has been made the owner of domain data, the database can reject the
deletion; remove that fixture-owned data or recreate the preview volume instead of weakening referential integrity.

## Remote Preview

Run the TLS terminator on the same host as the preview. It must accept public HTTPS and forward only to
`127.0.0.1:$RENTIVO_PREVIEW_PORT`; Compose never publishes the preview proxy, legacy app, or database on a non-loopback
address. Set `RENTIVO_TRUSTED_TLS_TERMINATOR_CIDR` to the narrow source address the proxy container observes for that
host-local connection, normally `172.30.0.1/32` with the default preview subnet. The terminator must replace and send the
original HTTPS scheme and port. Never forward the loopback HTTP port through a second public listener.

Use two files readable only by the deployment account:

- `/etc/rentivo/preview-db.env` contains exactly the four required `MYSQL_*` values and is passed to Compose only for
  interpolation and the MariaDB container.
- `/etc/rentivo/preview-app.env` contains `RENTIVO_SECRET_KEY` and application storage, email, encryption, cache, and
  observability settings, plus the secret-managed, URL-encoded `RENTIVO_DB_URL`. It must not contain
  `MYSQL_ROOT_PASSWORD` or any other `MYSQL_*` value.

Export the non-secret routing values from the deployment environment. All four database values are mandatory in the
remote override; omitted values stop Compose before it starts a container:

```bash
export RENTIVO_DB_ENV_FILE=/etc/rentivo/preview-db.env
export RENTIVO_APP_ENV_FILE=/etc/rentivo/preview-app.env
export RENTIVO_PREVIEW_ORIGIN=https://preview.example.com
export RENTIVO_PREVIEW_PORT=8080
export RENTIVO_WEBAUTHN_RP_ID=preview.example.com
export RENTIVO_TRUSTED_TLS_TERMINATOR_CIDR=172.30.0.1/32
chmod 600 "$RENTIVO_DB_ENV_FILE" "$RENTIVO_APP_ENV_FILE"
docker compose --env-file "$RENTIVO_DB_ENV_FILE" \
  -f docker-compose.next.yml -f docker-compose.next.remote.yml config --quiet
docker compose --env-file "$RENTIVO_DB_ENV_FILE" \
  -f docker-compose.next.yml -f docker-compose.next.remote.yml up -d --build db
docker compose --env-file "$RENTIVO_DB_ENV_FILE" \
  -f docker-compose.next.yml -f docker-compose.next.remote.yml \
  run --rm api alembic -c backend/alembic.ini upgrade head
docker compose --env-file "$RENTIVO_DB_ENV_FILE" \
  -f docker-compose.next.yml -f docker-compose.next.remote.yml up -d rentivo worker api frontend proxy
```

Seed remote parity accounts only when the environment is access-controlled. Supply the parity values from the secret
store with `docker compose run -e`, as in the local command, and remove them from the deployment shell afterward.

The remote override sets `RENTIVO_ENVIRONMENT=staging`, enables `Secure` cookies, and uses the
`__Host-rentivo_access`, `__Host-rentivo_challenge`, and `__Host-rentivo_csrf` names. WebAuthn requires the public origin
to match the browser origin exactly and the RP ID to be that origin's hostname or a valid registrable parent domain.
The browser and synthetic test runner must trust the TLS certificate chain; do not bypass certificate errors for passkey
validation.

## Health And Readiness

Inspect container health first:

```bash
docker compose -f docker-compose.next.yml ps
docker compose -f docker-compose.next.yml logs --tail=100 api proxy frontend
```

For local preview, verify both proxy routes:

```bash
curl --fail --show-error http://localhost:8080/api/v1/health
curl --fail --show-error --output /dev/null http://localhost:8080/
```

For remote preview, make the same requests through the public HTTPS origin. The API container is ready only after a
database `SELECT 1` and its `/api/v1/health` request both succeed. The proxy health check reaches that API endpoint
through Nginx, while the frontend health check verifies its root document. A healthy frontend alone does not establish
API or database readiness.

## Stop Or Roll Back

To stop only replacement traffic locally while retaining the database and legacy app:

```bash
docker compose -f docker-compose.next.yml stop proxy frontend api
curl --fail --show-error http://localhost:8000/health
```

For a remote rollback, first point the external TLS terminator back to the legacy service and verify the legacy health
endpoint. Then stop `proxy`, `frontend`, and `api`; keep `rentivo`, `worker`, `db`, and the named volumes running. Do not
use `down --volumes` during rollback because it deletes preview data. The repository's default Compose and deploy
workflow remain legacy-first, so no production route switch is part of this preview procedure.

## Pull Request Gate

Run the checks in `.github/workflows/test-pr.yaml` and attach any parity evidence to the pull request. The existing required
`all-checks-pass` job covers backend lint and coverage, frontend OpenAPI freshness and validation, a clean database upgrade,
merged Compose validation, and all four preview images. Follow
[Contributing](../../CONTRIBUTING.md), including the 100% backend coverage requirement. Automated agents may create a
pull request, but they must never merge it, enable auto-merge, push directly to `main`, or otherwise land the change. A
human reviews and merges every pull request.
