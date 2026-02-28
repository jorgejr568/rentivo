import logging
import sys

from rentivo.settings import settings

TEXT_FORMAT = "%(levelname)s %(name)s: %(message)s"


def configure_logging() -> None:
    """Configure the root logger based on settings.

    Call once at startup.  Call ``reconfigure()`` after any operation that
    may override the root logger (e.g. Alembic ``fileConfig``).
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stderr)

    if settings.log_json:
        from pythonjsonlogger.json import JsonFormatter

        handler.setFormatter(
            JsonFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                rename_fields={"asctime": "timestamp", "levelname": "level"},
            )
        )
    else:
        handler.setFormatter(logging.Formatter(TEXT_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Suppress uvicorn access logs — the app logs requests at the route level.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


# Alias — used after Alembic migrations may have overridden logging config.
reconfigure = configure_logging
