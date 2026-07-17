"""Centralized logging pipeline built on structlog + stdlib.

All application loggers (structlog and foreign stdlib loggers alike) render
through a single handler. Output is human-readable ``ConsoleRenderer`` by
default and JSON when ``settings.log_json`` is true.

Call ``configure_logging()`` once at process start. Call ``reconfigure()`` to
reapply after anything (e.g. Alembic ``fileConfig``) may have wiped handlers.
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.stdlib import ProcessorFormatter

from rentivo.observability import current_trace_ids
from rentivo.settings import settings


def _add_trace_context(logger, method_name, event_dict):
    """Stamp the active span's ids onto each log so logs correlate with traces.

    No-op when tracing is off or no span is active.
    """
    ids = current_trace_ids()
    if ids is not None:
        event_dict["trace_id"], event_dict["span_id"] = ids
    return event_dict


def _shared_processors(json_output: bool) -> list:
    base = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        _add_trace_context,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
    ]
    if json_output:
        base.insert(5, structlog.processors.dict_tracebacks)
    return base


def _pick_renderer(cli: bool):
    if cli or not settings.log_json:
        return structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    return structlog.processors.JSONRenderer()


def _cloudwatch_handler() -> logging.Handler:
    """A watchtower handler shipping JSON logs to CloudWatch Logs.

    Always JSON (independent of stdout's renderer) so a CloudWatch metric filter
    can match ``$.level``. Uses explicit creds when set, else the AWS chain.
    """
    import boto3
    import watchtower

    client_kwargs: dict = {"service_name": "logs", "region_name": settings.log_cloudwatch_region}
    if settings.log_cloudwatch_access_key_id and settings.log_cloudwatch_secret_access_key:
        client_kwargs["aws_access_key_id"] = settings.log_cloudwatch_access_key_id
        client_kwargs["aws_secret_access_key"] = settings.log_cloudwatch_secret_access_key

    handler = watchtower.CloudWatchLogHandler(
        log_group_name=settings.log_cloudwatch_group,
        log_stream_name=settings.log_cloudwatch_stream or "{machine_name}/{program_name}",
        boto3_client=boto3.client(**client_kwargs),
    )
    handler.setFormatter(
        ProcessorFormatter(
            keep_exc_info=True,
            foreign_pre_chain=_shared_processors(json_output=True),
            processors=[ProcessorFormatter.remove_processors_meta, structlog.processors.JSONRenderer()],
        )
    )
    return handler


def configure_logging(cli: bool = False) -> None:
    """Configure structlog + stdlib so both pipelines share one handler.

    Args:
        cli: Force ``ConsoleRenderer`` even when ``settings.log_json`` is true.
            The CLI reads logs interactively, so JSON would be useless there.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    json_output = not cli and settings.log_json
    shared = _shared_processors(json_output=json_output)
    renderer = _pick_renderer(cli)

    formatter = ProcessorFormatter(
        # Keep the raw exc_info tuple on the record so ConsoleRenderer and
        # dict_tracebacks can format it themselves. Without this, ProcessorFormatter
        # silently applies format_exc_info and structlog warns that pretty
        # tracebacks won't work.
        keep_exc_info=True,
        foreign_pre_chain=shared,
        processors=[
            ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Close (flushes watchtower's buffer, stops its thread) before replacing.
    for existing in root.handlers[:]:
        existing.close()
    root.handlers.clear()
    root.addHandler(handler)
    # Additive: stdout still gets every log; CloudWatch gets a JSON copy.
    if settings.log_cloudwatch_enabled:
        root.addHandler(_cloudwatch_handler())
    root.setLevel(level)

    structlog.configure(
        processors=shared + [ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Quiet noisy libraries — the app logs requests/queries explicitly.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


# Alias used after Alembic ``fileConfig`` may have wiped the root logger.
reconfigure = configure_logging
