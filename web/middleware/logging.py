"""Per-request logging context middleware.

Binds ``request_id``, ``method``, ``path`` and ``client_ip`` onto structlog's
contextvars so every log emitted during the request carries them. Adds an
``X-Request-ID`` response header, honoring an inbound one when provided.
"""

from __future__ import annotations

import structlog
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from ulid import ULID

logger = structlog.get_logger("web.request")

MAX_REQUEST_ID_LEN = 128

# Paths whose successful (200) responses are not logged. Keeps liveness-probe
# traffic from flooding access logs; non-200 responses still log so real
# failures surface.
SILENT_SUCCESS_PATHS = frozenset({"/health"})


def new_request_id() -> str:
    return str(ULID())


def _accept_inbound_id(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if not v or len(v) > MAX_REQUEST_ID_LEN:
        return None
    # Constrain to printable ASCII to avoid header injection surprises downstream.
    if not all(32 <= ord(c) < 127 for c in v):
        return None
    return v


class RequestContextMiddleware:
    """Pure ASGI middleware — binds per-request structlog context.

    Pure ASGI (not ``BaseHTTPMiddleware``) so the request body stream reaches
    downstream handlers untouched and coverage.py can track code run through
    the inner app. ``request_completed`` is logged and the ``X-Request-ID``
    header is injected at ``http.response.start`` — the point where the status
    is known but the body has not yet been flushed.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        structlog.contextvars.clear_contextvars()
        request = Request(scope, receive)
        rid = _accept_inbound_id(request.headers.get("X-Request-ID")) or new_request_id()
        request.state.request_id = rid
        path = request.url.path
        structlog.contextvars.bind_contextvars(
            request_id=rid,
            method=request.method,
            path=path,
            client_ip=request.client.host if request.client else None,
        )

        async def send_with_context(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_code = message["status"]
                structlog.contextvars.bind_contextvars(status_code=status_code)
                if not (path in SILENT_SUCCESS_PATHS and status_code == 200):
                    logger.info("request_completed")
                MutableHeaders(scope=message)["X-Request-ID"] = rid
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        except Exception:
            logger.exception("request_failed")
            raise
        finally:
            structlog.contextvars.clear_contextvars()
