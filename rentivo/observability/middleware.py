"""Pure-ASGI tracing middleware: opens the root server span per HTTP request.

Pure ASGI (not BaseHTTPMiddleware) to match the codebase convention — see the
notes in web/deps.py. No-ops for non-HTTP scopes and when tracing is disabled.
"""

from __future__ import annotations

from typing import Any

from rentivo.observability import extract_context, get_tracer, span

# High-frequency, zero-insight paths: container/LB health probes and static
# assets. Tracing them is pure noise and ingestion/indexing cost.
_UNTRACED_PATHS = ("/health",)
_UNTRACED_PREFIXES = ("/static/",)


class TracingMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or get_tracer() is None:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _UNTRACED_PATHS or path.startswith(_UNTRACED_PREFIXES):
            await self.app(scope, receive, send)
            return

        carrier = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope.get("headers", [])}
        parent = extract_context(carrier)
        method = scope.get("method", "GET")
        path = scope.get("path", "")
        status = {"code": 0}

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        attributes = {"http.request.method": method, "url.path": path}
        with span(f"HTTP {method}", parent=parent, attributes=attributes) as active_span:
            await self.app(scope, receive, send_wrapper)
            active_span.set_attribute("http.response.status_code", status["code"])
