# Observability (OpenTelemetry Tracing)

Rentivo emits OpenTelemetry **traces** covering each request/response, every
background job, and the layers underneath — services, repositories, every SQL
statement, the encryption/storage/email backends, and auth internals (including
the password-hash compare). Tracing is **fully optional**: off by default, with
no runtime dependency on a collector.

A single authenticated read fans out into dozens of nested spans, e.g.:

```
HTTP POST /login
├─ user.authenticate
│  ├─ user_repo.get_by_email → SELECT → base64.decrypt (×N)
│  └─ auth.verify_password            (bcrypt compare)
└─ login.complete_login
   ├─ audit.safe_log_for → audit.log → audit_log_repo.create → INSERT
   └─ known_device.notify_if_new → known_device_repo.upsert → UPDATE
```

## Quick start

### Docker compose (Jaeger + the app)

The runtime images bundle the `otel` extra, so the containerized app/worker can
export traces with just an env flag.

```bash
make jaeger-up                 # start Jaeger all-in-one (compose profile)
# in .env:
#   RENTIVO_OTEL_ENABLED=true
#   RENTIVO_OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318   # compose hostname
docker compose up -d --build rentivo worker                  # recreate to pick up .env
```

### Host process

```bash
uv sync --extra otel
make jaeger-up
RENTIVO_OTEL_ENABLED=true RENTIVO_OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
  make web-run
```

Open the UI at http://localhost:16686, pick service `rentivo`, and find a trace.

## How it works

- One module, `rentivo/observability/tracing.py`, owns every `opentelemetry`
  import behind a `try/except ImportError`. If the `otel` extra is absent or
  `RENTIVO_OTEL_ENABLED=false`, the tracer is `None` and every helper is a
  no-op — zero network calls, zero cost beyond a `None` check.
- `configure_tracing()` runs once at startup (web lifespan, worker boot)
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

## Configuration

See [`docs/configuration.md`](configuration.md#observability-opentelemetry) for
the four `RENTIVO_OTEL_*` variables.
