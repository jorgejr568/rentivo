# Observability (OpenTelemetry Tracing)

Rentivo emits OpenTelemetry **traces** spanning each request/response, every
background job, and the I/O backends underneath (KMS, S3, SES, PDF). Tracing is
**fully optional**: off by default, with no runtime dependency on a collector.

## Quick start (local, Jaeger)

```bash
uv sync --extra otel          # install the otel packages
make jaeger-up                 # start Jaeger all-in-one (compose profile)

# enable in your .env (host process):
#   RENTIVO_OTEL_ENABLED=true
#   RENTIVO_OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
make web-run
```

Open the UI at http://localhost:16686, pick service `rentivo`, and find a trace.
On the compose network use `http://jaeger:4318` as the endpoint.

## How it works

- One module, `rentivo/observability/tracing.py`, owns every `opentelemetry`
  import behind a `try/except ImportError`. If the `otel` extra is absent or
  `RENTIVO_OTEL_ENABLED=false`, the global tracer is `None` and every helper is a
  no-op — zero network calls, zero cost beyond a `None` check.
- `configure_tracing()` runs once at startup (web lifespan, worker boot, CLI boot)
  and installs an OTLP/HTTP exporter (`BatchSpanProcessor`).
- The pure-ASGI `TracingMiddleware` (outermost) opens the root `HTTP <method>`
  span. Decorated functions nest under it automatically via OpenTelemetry's
  active-span contextvar.
- Across the job queue, `JobService.enqueue` stashes a W3C `traceparent` in the
  job payload's `_otel` key; the worker extracts it so the `job <type>` span (and
  everything under it) re-parents onto the request that enqueued it.

## Instrument a new function

```python
from rentivo.observability import traced

@traced("my.operation")           # name optional; defaults to __qualname__
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
| `kms.encrypt` / `kms.decrypt` / `kms.decrypt_many` | `KMSBackend` |
| `s3.save` / `s3.get` / `s3.get_url` / `s3.delete` | `S3Storage` |
| `ses.send` | `SESEmailBackend` |
| `email.send` / `email.send_communication` | `EmailService` |
| `pdf.generate` / `pdf.merge_receipts` | PDF layer |
| `bill.generate` / `bill.render_pdf_sync` / `communication.send` | service layer |

## Privacy

Span attributes carry only non-PII: HTTP method/path, job type/ulid/attempts,
operation names, counts, byte sizes, backend names. **Never** put plaintext,
emails, PIX fields, receipt filenames, or message bodies into a span. Local
storage and the local email backend are not instrumented (no network I/O).

## Configuration

See [`docs/configuration.md`](configuration.md#observability-opentelemetry) for
the four `RENTIVO_OTEL_*` variables.
