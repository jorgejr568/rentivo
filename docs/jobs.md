# Job Drivers

Rentivo runs background work — `email.send`, `communication.send`, `pdf.render`, and `s3.delete` — through a pluggable **job driver** selected by `RENTIVO_JOB_BACKEND`. State-changing web flows enqueue work; the worker process executes it. Two drivers are available: `database` (the default) and `temporal` (optional).

## Database driver (`database`, default)

The default and fully supported production driver. It needs **zero extra dependencies** beyond what Rentivo already requires — no message broker, no external cluster.

- Enqueue inserts a row into the `jobs` table (`DatabaseJobBackend` over `SQLAlchemyJobRepository`).
- A polling `Worker` (`rentivo/jobs/worker.py`) claims due jobs in batches, runs the registered handler, and updates the row.
- Retries use an exponential backoff schedule (see the parity table below); on exhaustion or a `PermanentJobError` the job is dead-lettered.

Tunables (see [`configuration.md`](configuration.md) for the full reference):

| Env var | Default | Purpose |
|---|---|---|
| `RENTIVO_JOB_WORKER_BATCH_SIZE` | `10` | Jobs claimed per poll |
| `RENTIVO_JOB_WORKER_IDLE_SLEEP_SECONDS` | `5.0` | Sleep when the queue is empty |
| `RENTIVO_JOB_WORKER_STUCK_AFTER_SECONDS` | `600` | Reclaim window for jobs left `running` by a dead worker |

Run the worker:

```bash
make worker            # local
python -m rentivo.workers
```

In production this is the `Dockerfile.worker` image.

## Temporal driver (`temporal`, optional)

> **Temporal is entirely optional.** The database driver is the supported default and is sufficient for production. Only adopt Temporal if you already run a Temporal cluster and want its durable execution, visibility UI, and retry tooling. You do **not** need Temporal to run Rentivo — not even in production.

The Temporal driver offloads job execution to a Temporal cluster instead of the `jobs` table. It requires the optional `temporal` extra and a reachable cluster:

```bash
uv sync --extra temporal
```

- Enqueue starts one workflow per job — `TemporalJobBackend.enqueue()` (`rentivo/jobs/temporal/backend.py`) calls the Temporal client's `start_workflow(...)`.
- A per-job-type workflow (`rentivo/jobs/temporal/workflows.py`) wraps the **unchanged** registry handler in an activity (`rentivo/jobs/temporal/activities.py`).
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
| Backoff schedule | `60s / 5m / 15m / 1h / 6h`, max 5 attempts (`rentivo/jobs/backoff.py`) | Identical — same `rentivo/jobs/backoff.py` |
| `PermanentJobError` | Dead-letter immediately (no retry) | Mapped to a non-retryable failure, dead-lettered immediately |
| Fail hooks + audit events | `JOB_SUCCEEDED` / `JOB_RETRY_SCHEDULED` / `JOB_FAILED` fire | Same events fire via the `rentivo.finalize_job` activity |
| OTel context | `_otel` carrier propagated from enqueue to handler | `_otel` carrier propagated identically |

## Handlers are shared

The same registry handlers (`rentivo/jobs/handlers/`) run under **both** drivers — the handler code is identical and unaware of the driver. Adding a new background job:

1. **Always:** register the handler with `@register("job.type")` in `rentivo/jobs/handlers/`. This is all the database driver needs.
2. **For Temporal as well:** add a `@workflow.defn` workflow class plus its activity in `rentivo/jobs/temporal/`, and add a `_WORKFLOW_BY_TYPE` entry mapping the job type to that workflow (`rentivo/jobs/temporal/backend.py`).

The shared backoff schedule lives once in `rentivo/jobs/backoff.py` and is reused by both drivers, so retry semantics stay in lockstep.

## Local development with Temporal

A local Temporal cluster ships as an **opt-in** docker-compose profile, so it is never started unless you ask for it:

```bash
make temporal-up      # start the `temporal` compose profile (cluster + UI)
```

The Temporal Web UI is at <http://localhost:8233>. Point Rentivo at the local cluster:

```bash
# .env (or your shell)
RENTIVO_JOB_BACKEND=temporal
RENTIVO_TEMPORAL_HOST=localhost:7233   # use temporal:7233 from inside the compose network
```

Then run the worker — the same entrypoint dispatches on the backend:

```bash
uv sync --extra temporal
python -m rentivo.workers     # logs `temporal_worker_boot` and serves the task queue
```

Trigger an enqueue from the app (for example, request a password reset) and watch the workflow appear and complete in the Temporal UI. Stop the cluster when done:

```bash
make temporal-down
```

## Docker

Both project images — web (`Dockerfile`) and worker (`Dockerfile.worker`) — **bundle the `temporal` extra by default**, so you can switch `RENTIVO_JOB_BACKEND` between `database` and `temporal` at runtime without rebuilding. This is just a packaging convenience: the database driver is still the default and Temporal is still optional — the bundled `temporalio` is dormant until you point the app at a Temporal cluster.

Each image exposes a build arg to override the extras (e.g. to slim a database-only deployment by dropping `temporal`):

| Image | Build arg | Default |
|---|---|---|
| `Dockerfile` (web) | `APP_EXTRAS` | `cache otel temporal` |
| `Dockerfile.worker` | `WORKER_EXTRAS` | `cache otel temporal` |

```bash
# Default build — Temporal-capable out of the box:
docker build -f Dockerfile -t rentivo-web .

# Slim, database-only build (drop temporal):
docker build -f Dockerfile --build-arg APP_EXTRAS="cache otel" -t rentivo-web .
```

## Scheduled jobs

Most work is enqueued reactively by web flows. One job runs on a **daily schedule**: the payment-reminders sweep (REN-6).

`python -m rentivo.scripts.send_payment_reminders` scans issued-but-unpaid bills and, on the configured offsets relative to each due date, enqueues one `communication.send` job per recipient — the worker delivers them. It is a **one-shot** script (runs, then exits) and **idempotent**: re-running on the same day will not re-send a reminder already queued/sent for that bill+offset, so an accidental double-run is safe.

| Env knob | Default | Meaning |
|---|---|---|
| `RENTIVO_PAYMENT_REMINDERS_ENABLED` | `true` | Global on/off **kill switch** for the sweep. |
| `RENTIVO_PAYMENT_REMINDER_OFFSET_DAYS` | `3,0,-3` | Days from due date to remind: positive = before due (D-3), `0` = due date, negative = overdue (D+3). |
| `RENTIVO_PAYMENT_REMINDER_CHANNEL` | `email` | Delivery channel. |

`--dry-run` plans and prints the reminders **without enqueuing** anything; `--date=YYYY-MM-DD` overrides "today" for catch-up or testing.

### Deploy: docker-compose

The `reminders` service in `docker-compose.yml` runs the sweep using the **same image and env as the worker**. It is profile-gated (`profiles: ["tools"]`) so `docker compose up` never starts it; the deploy host invokes it once a day:

```bash
docker compose run --rm reminders                                 # the daily sweep
docker compose run --rm reminders \
  python -m rentivo.scripts.send_payment_reminders --dry-run      # verify, enqueues nothing
```

Schedule it on the deploy host with a **systemd timer** (preferred — journald logs + `Persistent=true` catch-up after downtime):

```ini
# /etc/systemd/system/rentivo-payment-reminders.service
[Unit]
Description=Rentivo daily payment-reminders sweep
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/rentivo
ExecStart=/usr/bin/docker compose run --rm reminders
```

```ini
# /etc/systemd/system/rentivo-payment-reminders.timer
[Unit]
Description=Run the Rentivo payment-reminders sweep daily

[Timer]
OnCalendar=*-*-* 10:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl enable --now rentivo-payment-reminders.timer
```

The sweep derives "today" from `America/Sao_Paulo`, so only the calendar day matters — 10:00 local is a safe business-hours window. Set the host timezone to `America/Sao_Paulo`, or use `OnCalendar=*-*-* 13:00:00 UTC`.

Cron alternative:

```cron
# Rentivo payment-reminders daily sweep — 10:00 America/Sao_Paulo
CRON_TZ=America/Sao_Paulo
0 10 * * * cd /opt/rentivo && /usr/bin/docker compose run --rm reminders >> /var/log/rentivo/payment-reminders.log 2>&1
```

### Deploy: Kubernetes

For a k8s deployment, use a `CronJob` with the **same image and env as the worker** Deployment:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: payment-reminders
spec:
  schedule: "0 13 * * *"          # 13:00 UTC = 10:00 America/Sao_Paulo
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: payment-reminders
              image: <worker-image>:<tag>     # same image as the worker Deployment
              command: ["python", "-m", "rentivo.scripts.send_payment_reminders"]
              envFrom:
                - secretRef:
                    name: rentivo-env          # same env as the worker
```

### Rollback / disable

Set `RENTIVO_PAYMENT_REMINDERS_ENABLED=false` for an **instant kill switch** — the next run no-ops, no redeploy needed. To remove the schedule entirely, `systemctl disable --now rentivo-payment-reminders.timer` (or drop the cron line / delete the CronJob). No schema or data migration is involved, so there is nothing to revert.

## Known limitations

Neither the database worker nor the Temporal worker performs graceful SIGTERM draining yet: a job in flight when the process is signalled is interrupted and re-claimed/retried rather than being allowed to finish first. Job execution is idempotent-friendly (handlers re-run safely), but a graceful-drain shutdown is future work for both drivers.
