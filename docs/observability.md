# Observability

Rentivo emits structured application logs and optional OpenTelemetry **traces**
covering FastAPI requests, background jobs, and the layers underneath: services,
repositories, SQL statements, encryption/storage/email backends, and auth
internals. FastAPI attaches `X-Request-ID` to responses and includes the same ID
in structured request context. Tracing is off by default and has no runtime
dependency on a collector.

A single authenticated read fans out into dozens of nested spans, e.g.:

```
HTTP POST /api/v1/auth/login
├─ user.authenticate
│  ├─ user_repo.get_by_email → SELECT → base64.decrypt (×N)
│  └─ auth.verify_password            (bcrypt compare)
└─ login.complete_login
   ├─ audit.safe_log_for → audit.log → audit_log_repo.create → INSERT
   └─ known_device.notify_if_new → known_device_repo.upsert → UPDATE
```

## Quick start

### Compose topology (Jaeger + API and worker)

The runtime images bundle the `otel` extra, so the containerized app/worker can
export traces with just an env flag. Complete the development setup first so
both `.env` and `.env.db` exist; every command below uses that split-env
contract.

```bash
make jaeger-up                 # start Jaeger all-in-one (compose profile)
# in .env:
#   RENTIVO_OTEL_ENABLED=true
#   RENTIVO_OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318   # compose hostname
make compose-dev                  # recreate the app and worker to pick up .env
```

### Host process

```bash
uv sync --project backend --extra otel
make jaeger-up
RENTIVO_OTEL_ENABLED=true RENTIVO_OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
  uv run --project backend uvicorn rentivo.api.app:create_app \
    --factory --host 127.0.0.1 --port 8001
```

Open the UI at http://localhost:16686, pick service `rentivo`, and find a trace.

## How it works

- One module, `backend/rentivo/observability/tracing.py`, owns every `opentelemetry`
  import behind a `try/except ImportError`. If the `otel` extra is absent or
  `RENTIVO_OTEL_ENABLED=false`, the tracer is `None` and every helper is a
  no-op: zero network calls and no cost beyond a `None` check.
- `configure_tracing()` runs once at startup (FastAPI lifespan, worker boot)
  and installs an OTLP/HTTP exporter (`BatchSpanProcessor`).
- The pure-ASGI `TracingMiddleware` (outermost) opens the root `HTTP <method>`
  span. `@traced` functions and SQLAlchemy query spans nest under it automatically
  via OpenTelemetry's active-span contextvar.
- DB spans come from `SQLAlchemyInstrumentor`, wired into `db.get_engine()` via
  `instrument_sqlalchemy()`. It is handed our provider explicitly because
  `configure_tracing` never installs a *global* provider.
- Across the job queue, `JobService.enqueue` stashes a W3C `traceparent` in the
  job payload's `_otel` key; the worker extracts it so the `job <type>` span (and
  everything under it) re-parents onto the request that enqueued it.

## Instrument a new function

```python
from rentivo.observability import traced

@traced("my.operation")           # name optional; defaults to the function name
def do_work(...):
    ...
```

Works on sync and async functions. For dynamic, **non-PII** attributes:

```python
from rentivo.observability import set_attributes

@traced("my.operation")
def do_work(items):
    set_attributes(count=len(items))   # never pass PII
    ...
```

For a sub-span inside a function, use the context manager:

```python
from rentivo.observability import span

with span("my.substep"):
    ...
```

## What is instrumented

| Span | Source |
|------|--------|
| `HTTP <method>` | `TracingMiddleware` (root of every web trace) |
| `job <type>` | worker dispatch (root of every worker trace, re-parented to the enqueuer) |
| `SELECT/INSERT/UPDATE …`, `connect` | every SQL statement (SQLAlchemy auto-instrumentation) |
| `<entity>.<method>` | every public **service** method (e.g. `billing.create`, `pix.resolve_for_billing`) |
| `<entity>_repo.<method>` | every public **repository** method (e.g. `bill_repo.get_by_uuid`) |
| `user.authenticate` / `auth.verify_password` / `login.complete_login` | auth flow incl. the bcrypt compare |
| `base64.encrypt` / `base64.decrypt`, `cache.decrypt*` | local-dev encryption backend + decrypt cache |
| `kms.encrypt` / `kms.decrypt` / `kms.decrypt_many` | `KMSBackend` (production encryption) |
| `local.save` / `local.get` / `local.get_url` / `local.delete` | `LocalStorage` |
| `s3.save` / `s3.get` / `s3.get_url` / `s3.delete` | `S3Storage` |
| `ses.send`, `email.send` / `email.send_communication` | SES backend + `EmailService` |
| `pdf.generate` / `pdf.merge_receipts` | PDF layer |

## Span volume & sampling

Instrumentation is deep, so a single page can emit **hundreds** of spans —
notably `base64.decrypt`/`kms.decrypt` fire once per encrypted field per row.
That is intentional (full visibility) but increases trace size and exporter
load. Dial it back with head sampling:

```bash
RENTIVO_OTEL_SAMPLE_RATIO=0.1   # trace ~10% of requests (parent-based)
```

## Sending to AWS CloudWatch (X-Ray Transaction Search)

Set `RENTIVO_OTEL_EXPORTER=cloudwatch` to export straight to AWS — no collector.
The exporter posts OTLP/protobuf to `https://xray.<region>.amazonaws.com/v1/traces`,
**SigV4-signed** via `botocore`, with the AWS **X-Ray id generator** (X-Ray needs
timestamp-prefixed trace ids).

```bash
RENTIVO_OTEL_ENABLED=true
RENTIVO_OTEL_EXPORTER=cloudwatch
RENTIVO_OTEL_AWS_REGION=us-east-1
RENTIVO_OTEL_SAMPLE_RATIO=0.05          # collector-less defaults to 100%; AWS warns ~20x cost
# creds: omit to use the standard chain (env / instance profile / ECS task role), or:
# RENTIVO_OTEL_AWS_ACCESS_KEY_ID=...
# RENTIVO_OTEL_AWS_SECRET_ACCESS_KEY=...
```

**AWS-side prerequisites (one-time):**

1. **Enable Transaction Search** in CloudWatch (X-Ray → Transaction Search). Spans
   land in the `aws/spans` log group and become searchable; without it the
   endpoint accepts spans but they aren't queryable.
2. **IAM:** grant the app/worker role the managed `AWSXrayWriteOnlyPolicy`.
3. Pick a sampling rate — direct send is 100% by default; `RENTIVO_OTEL_SAMPLE_RATIO`
   is the knob (parent-based head sampling).

View traces in the CloudWatch console under **X-Ray traces / Transaction Search**.
The `otlp` (Jaeger/collector) and `cloudwatch` modes are mutually exclusive per
process — flip `RENTIVO_OTEL_EXPORTER`.

## Privacy

Span **attributes** carry only non-PII: HTTP method/path, job type/ulid/attempts,
operation names, counts, sizes, backend names. **Never** put plaintext, emails,
PIX fields, receipt filenames, or message bodies into a span. SQLAlchemy spans
record the statement text with **bound parameters omitted**, so literal PII never
reaches a span. Span *names* are static strings — no arguments are captured.

## Runtime topology and profiles

The default stack is `db`, one-shot `migrate`, `api`, `worker`, `frontend`, and
`proxy`. Nginx exposes `127.0.0.1:8080`; API, worker, and frontend stay on
internal networks. The API provides:

- `/health` and `/api/v1/health` for JSON liveness;
- `/api/v1/ready` for dependency-aware database readiness;
- `X-Request-ID` response correlation and problem-details request IDs.

The Nginx health check uses API readiness so a frontend fallback cannot produce
a false positive. The `observability` Compose profile adds Jaeger only when
requested:

```bash
make jaeger-up      # UI 16686; OTLP/HTTP 4318; OTLP/gRPC 4317
make jaeger-down
```

The separate `temporal` profile adds a development Temporal cluster and UI:

```bash
make temporal-up    # frontend 7233; UI 8233
make temporal-down
```

Inside Compose, exporters address Jaeger at `http://jaeger:4318` and Temporal at
`temporal:7233`. Host processes use `localhost` on the published ports.

## Production signals

At minimum, production dashboards and alerts must cover:

| Area | Signals |
|---|---|
| Edge/API | readiness, request rate, 4xx/5xx rate, p50/p95/p99 latency, request IDs |
| Frontend | runtime errors, failed navigation/API calls, Core Web Vitals |
| Worker | heartbeat, pending/running/failed jobs, oldest queue age, attempts |
| Temporal | pollers, workflow failures, schedule-to-start latency (when enabled) |
| MariaDB | availability, connections, locks, slow queries, disk/capacity |
| Dependencies | KMS, SES, S3, Redis, and OTLP error/latency rates |
| Release | immutable SHA/image digests, migration revision, rollout timestamps |

The production release baseline is: readiness must not fail twice or remain
down for 60 seconds; sustained 5xx above 1% for five minutes or above 5% for one
minute aborts rollout; p95 latency over twice baseline for five minutes aborts;
worker heartbeat missing for two minutes, stale running work, or queue age over
five minutes requires maintenance and investigation. See the
[production release runbook](runbooks/production-release.md) for the complete
go/abort and recovery procedure.

Logs and traces must carry the release SHA or immutable image identity through
deployment metadata. Use request IDs to correlate browser reports, Nginx access
logs, FastAPI logs, job audit events, and traces. Alerting must not rely only on
container health: green health endpoints do not prove auth, invoice, storage,
email, or worker workflows are functioning.

## Configuration

See [`docs/configuration.md`](configuration.md#observability-opentelemetry) for
the four `RENTIVO_OTEL_*` variables.
