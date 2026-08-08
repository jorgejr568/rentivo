# Job Drivers

Rentivo runs background work such as `email.send`, `communication.send`,
`pdf.render`, `recibo.render`, `export.generate`, `export.send`, `s3.delete`, and
`auth.cleanup` through a pluggable **job driver** selected by
`RENTIVO_JOB_BACKEND`. State-changing API flows enqueue work; the worker process
executes it. The exception is `auth.cleanup`, which recurs on a timer rather
than following a request — see [Cleanup scheduling](#cleanup-scheduling). Two
drivers are available: `database` (the default) and `temporal` (optional).

## Database driver (`database`, default)

The default and fully supported production driver. It needs **zero extra dependencies** beyond what Rentivo already requires — no message broker, no external cluster.

- Enqueue inserts a row into the `jobs` table (`DatabaseJobBackend` over `SQLAlchemyJobRepository`).
- A polling `Worker` (`backend/rentivo/jobs/worker.py`) claims due jobs in batches, runs the registered handler, and updates the row.
- Retries use an exponential backoff schedule (see the parity table below); on exhaustion or a `PermanentJobError` the job is dead-lettered.
- The worker also **self-schedules** the recurring `auth.cleanup` job (see [Cleanup scheduling](#cleanup-scheduling)); every other job type is enqueued by an API flow.

Tunables (see [`configuration.md`](configuration.md) for the full reference):

| Env var | Default | Purpose |
|---|---|---|
| `RENTIVO_JOB_WORKER_BATCH_SIZE` | `10` | Jobs claimed per poll |
| `RENTIVO_JOB_WORKER_IDLE_SLEEP_SECONDS` | `5.0` | Sleep when the queue is empty |
| `RENTIVO_JOB_WORKER_STUCK_AFTER_SECONDS` | `600` | Reclaim window for jobs left `running` by a dead worker |
| `RENTIVO_AUTH_CLEANUP_INTERVAL_SECONDS` | `3600` | How often the worker makes sure an `auth.cleanup` job is queued (`0` disables) |

### Payload encryption at rest

`jobs.payload` is encrypted through the configured encryption backend
(`RENTIVO_ENCRYPTION_BACKEND`, KMS in production) before it is written. The
stored value is a JSON envelope:

```json
{"__enc": "enc:v1:<base64 KMS ciphertext>"}
```

The envelope is a JSON *object* rather than a bare ciphertext string because
MariaDB renders the `sa.JSON` column as `longtext ... CHECK (json_valid(...))`;
a bare ciphertext fails that constraint with `ERROR 4025`, while SQLite (the
test suite) would accept it. Encryption and decryption happen inside
`SQLAlchemyJobRepository`, so handlers always receive a plaintext dict and no
producer needs to know about it.

Payloads carry third-party recipient addresses, client IPs, user agents, and —
for `password_reset` — a reset URL, none of which belong in a database backup
that a low-privilege operator or read replica can read.

Reads accept both shapes, so encrypted and legacy plaintext rows coexist and
no flag day is needed. To encrypt the historical backlog:

```bash
make encrypt-job-payloads-dry   # report only
make encrypt-job-payloads       # apply
```

If the encryption backend is unavailable, the worker declines to claim the
affected rows: they stay `pending` with their attempt count untouched, and the
worker retries on the next poll. A row that can never be decrypted (for example
after key destruction) is skipped on every poll and logged as
`job_payload_decode_failed` with its `job_id` and `ulid`; quarantine it with
`UPDATE jobs SET status='failed', last_error='undecryptable payload' WHERE id = ...`.

### Cleanup scheduling

`auth.cleanup` is the one recurring job: it deletes expired login tokens, stale
authentication challenges, and old job rows. Nothing in the API enqueues it, so
each driver is responsible for producing it.

- **Database driver:** the worker self-schedules it. Once every
  `RENTIVO_AUTH_CLEANUP_INTERVAL_SECONDS` (default `3600`; `0` disables
  self-scheduling) it checks the `jobs` table and enqueues `auth.cleanup` with an
  empty payload unless one is already `pending`/`running` or a previous run
  finished inside the *recency window*, which is half the interval. The window is
  deliberately shorter than the check period: a full-interval window would always
  cover the run enqueued at the previous check and suppress it, so cleanup would
  land every two intervals. With the half-interval window the job is enqueued
  roughly once per interval — hourly at the default — while a restarted worker,
  whose check timer resets, still does not pile on a duplicate. Running several
  workers is safe: the check makes duplicates unlikely and the handler is
  idempotent. Each enqueue is logged as `auth_cleanup_scheduled`.
- **Temporal driver:** the worker does **not** self-schedule. Create a Temporal
  schedule (or cron workflow) that starts `AuthCleanupWorkflow` on
  `RENTIVO_TEMPORAL_TASK_QUEUE` with the arguments `({}, "<id>", 5)` — empty
  payload, an identifier used only for the audit entries, and the maximum
  attempts — hourly, matching the database driver's default cadence. Without that
  schedule the cleanups below never run, and
  `RENTIVO_AUTH_CLEANUP_INTERVAL_SECONDS` has no effect.

### Retention

Each `auth.cleanup` run deletes expired login tokens, stale authentication
challenges, and `succeeded`/`failed` job rows whose `updated_at` is older than
`RENTIVO_JOB_RETENTION_DAYS` (default 30; `0` disables the job purge). All three
purges drain in batches of 100 until no eligible row remains or the run has
removed 10,000 rows from that table (`AUTH_CLEANUP_MAX_PURGED_ROWS`), so a large
backlog is worked down over consecutive runs. The whole run — all three drains —
happens inside a single transaction; the per-table cap is what bounds how long
that transaction stays open, while the batch size only bounds the size of each
statement's `IN` list. `pending` and `running` job rows are never touched, so a
job scheduled far in the future and the cleanup job's own row are safe.

Run the worker:

```bash
make worker            # local
uv run --project backend python -m rentivo.workers
```

In production this is the `backend/Dockerfile.worker` image.

## Temporal driver (`temporal`, optional)

> **Temporal is entirely optional.** The database driver is the supported default and is sufficient for production. Only adopt Temporal if you already run a Temporal cluster and want its durable execution, visibility UI, and retry tooling. You do **not** need Temporal to run Rentivo — not even in production.

The Temporal driver offloads job execution to a Temporal cluster instead of the `jobs` table. It requires the optional `temporal` extra and a reachable cluster:

```bash
uv sync --project backend --extra temporal
```

- Enqueue starts one workflow per job — `TemporalJobBackend.enqueue()` (`backend/rentivo/jobs/temporal/backend.py`) calls the Temporal client's `start_workflow(...)`.
- A per-job-type workflow (`backend/rentivo/jobs/temporal/workflows.py`) wraps the **unchanged** registry handler in an activity (`backend/rentivo/jobs/temporal/activities.py`).
- The workflow owns the retry loop, mirroring the database backoff exactly.

Settings (only read when `RENTIVO_JOB_BACKEND=temporal`):

| Env var | Default | Purpose |
|---|---|---|
| `RENTIVO_TEMPORAL_HOST` | `localhost:7233` | Temporal frontend `host:port` |
| `RENTIVO_TEMPORAL_NAMESPACE` | `default` | Temporal namespace |
| `RENTIVO_TEMPORAL_TASK_QUEUE` | `rentivo-jobs` | Task queue for workflows and workers |
| `RENTIVO_TEMPORAL_TLS` | `false` | Use TLS when connecting to the frontend |
| `RENTIVO_TEMPORAL_ACTIVITY_START_TO_CLOSE_TIMEOUT_SECONDS` | `600` | Per-activity start-to-close timeout |

When `RENTIVO_JOB_BACKEND=temporal`, `RENTIVO_TEMPORAL_HOST`, `_NAMESPACE`, and `_TASK_QUEUE` must be non-empty (enforced by a Settings validator at startup).

## Driver parity

Both drivers present the same `JobBackend.enqueue(...)` seam and the same observable semantics. Handler authors never see the difference.

| Concern | Database | Temporal |
|---|---|---|
| Enqueue | `INSERT` a `jobs` row | `start_workflow` (one workflow per job) |
| Retries | Polling worker re-claims with backoff | Workflow retry loop |
| Backoff schedule | `60s / 5m / 15m / 1h / 6h`, max 5 attempts (`backend/rentivo/jobs/backoff.py`) | Identical — same `backend/rentivo/jobs/backoff.py` |
| `PermanentJobError` | Dead-letter immediately (no retry) | Mapped to a non-retryable failure, dead-lettered immediately |
| Fail hooks + audit events | `JOB_SUCCEEDED` / `JOB_RETRY_SCHEDULED` / `JOB_FAILED` fire | Same events fire via the `rentivo.finalize_job` activity |
| OTel context | `_otel` carrier propagated from enqueue to handler | `_otel` carrier propagated identically |

## Handlers are shared

The same registry handlers (`backend/rentivo/jobs/handlers/`) run under **both** drivers — the handler code is identical and unaware of the driver. Adding a new background job:

1. **Always:** register the handler with `@register("job.type")` in `backend/rentivo/jobs/handlers/`. This is all the database driver needs.
2. **For Temporal as well:** add a `@workflow.defn` workflow class plus its activity in `backend/rentivo/jobs/temporal/`, and add a `_WORKFLOW_BY_TYPE` entry mapping the job type to that workflow (`backend/rentivo/jobs/temporal/backend.py`).

The shared backoff schedule lives once in `backend/rentivo/jobs/backoff.py` and is reused by both drivers, so retry semantics stay in lockstep.

## Local development with Temporal

A local Temporal cluster ships as an **opt-in** docker-compose profile, so it is never started unless you ask for it:

```bash
make temporal-up      # start the `temporal` compose profile (cluster + UI)
```

The target uses the development Compose contract: application settings from
`.env`, database/interpolation values from `.env.db`, and both the base and
development override manifests. Create those files from their checked-in
examples as described in [development.md](development.md).

The Temporal Web UI is at <http://localhost:8233>. Point Rentivo at the local cluster:

```bash
# .env (or your shell)
RENTIVO_JOB_BACKEND=temporal
RENTIVO_TEMPORAL_HOST=localhost:7233   # use temporal:7233 from inside the compose network
```

Then run the worker — the same entrypoint dispatches on the backend:

```bash
uv sync --project backend --extra temporal
uv run --project backend python -m rentivo.workers  # logs `temporal_worker_boot` and serves the task queue
```

Trigger an enqueue from the app (for example, request a password reset) and watch the workflow appear and complete in the Temporal UI. Stop the cluster when done:

```bash
make temporal-down
```

## Containers and Compose profiles

The default production topology has separate FastAPI and worker images:

| Image | Build file | Runtime |
|---|---|---|
| API and migration | `backend/Dockerfile.api` | FastAPI or one-shot Alembic |
| Worker | `backend/Dockerfile.worker` | Selected job driver |

Both runtime images include the optional cache, OpenTelemetry, and Temporal
extras by default. Selecting `database` keeps Temporal dormant; selecting
`temporal` requires a reachable cluster.

The production default starts one `worker` service. Local Temporal is an
opt-in Compose profile and is never started with the base stack:

```bash
make temporal-up       # temporal:7233 and UI at localhost:8233
make temporal-down
```

The profile is for development. Production Temporal must use a durable,
operated cluster rather than the profile's local SQLite service.

## Operations and draining

Monitor the database driver by status (`pending`, `running`, `succeeded`, and
`failed`), oldest due `pending` age, attempts, job type, and worker heartbeat.
Alert when the heartbeat is absent for two minutes, a running claim exceeds
`RENTIVO_JOB_WORKER_STUCK_AFTER_SECONDS`, failures increase, or oldest queue age
exceeds five minutes. For Temporal, monitor the same job outcomes plus task-queue
pollers, workflow failures, and schedule-to-start latency.

Neither driver currently performs graceful `SIGTERM` draining. Before a
production rollout:

1. Put the application in edge maintenance mode and stop schedules/integrations
   that can enqueue jobs.
2. Wait for running database jobs or Temporal workflows to reach zero.
3. Record outstanding pending/failed work and oldest queue age.
4. Stop the worker only after the queue is quiescent.

If a worker is interrupted, the database driver reclaims the job after the
stuck threshold and Temporal retries according to workflow semantics. Handlers
are designed for at-least-once execution, but operators must investigate any
uncertain external side effect before resuming. The full release procedure is
in the [production release runbook](runbooks/production-release.md).
