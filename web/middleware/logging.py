"""Per-request logging context middleware.

Binds ``request_id``, ``method``, ``path`` and ``client_ip`` onto structlog's
contextvars so every log emitted during the request carries them. Adds an
``X-Request-ID`` response header, honoring an inbound one when provided.
"""

from __future__ import annotations

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp
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


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        structlog.contextvars.clear_contextvars()
        rid = _accept_inbound_id(request.headers.get("X-Request-ID")) or new_request_id()
        request.state.request_id = rid
        structlog.contextvars.bind_contextvars(
            request_id=rid,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
        )
        try:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("request_failed")
                raise
            structlog.contextvars.bind_contextvars(status_code=response.status_code)
            if not (request.url.path in SILENT_SUCCESS_PATHS and response.status_code == 200):
                logger.info("request_completed")
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            structlog.contextvars.clear_contextvars()
