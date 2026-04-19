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

from rentivo.settings import settings


def _shared_processors() -> list:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.dict_tracebacks,
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
    ]


def _pick_renderer(cli: bool):
    if cli or not settings.log_json:
        return structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    return structlog.processors.JSONRenderer()


def configure_logging(cli: bool = False) -> None:
    """Configure structlog + stdlib so both pipelines share one handler.

    Args:
        cli: Force ``ConsoleRenderer`` even when ``settings.log_json`` is true.
            The CLI reads logs interactively, so JSON would be useless there.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    shared = _shared_processors()
    renderer = _pick_renderer(cli)

    formatter = ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
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
