"""Tests for the per-request structlog context middleware."""

from __future__ import annotations

import asyncio
import json
import logging
from io import StringIO

import pytest
import structlog
from fastapi import FastAPI
from starlette.responses import Response
from starlette.testclient import TestClient

from rentivo.logging import configure_logging
from web.middleware.logging import RequestContextMiddleware


@pytest.fixture()
def app_and_buffer(monkeypatch):
    """Minimal app with the middleware; capture logs in a StringIO buffer."""
    buf = StringIO()

    class _Settings:
        log_level = "DEBUG"
        log_json = True
        log_cloudwatch_enabled = False

    monkeypatch.setattr("rentivo.logging.settings", _Settings())

    # Redirect stderr used inside configure_logging to our buffer.
    import sys as _sys

    monkeypatch.setattr("rentivo.logging.sys", type("S", (), {"stderr": buf}))
    configure_logging()
    # configure_logging installed a StreamHandler on root pointing at our buf.

    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ok")
    async def ok():
        structlog.get_logger("test").info("handler_ran")
        return {"ok": True}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    @app.get("/health")
    async def health(status: int = 200):
        # Configurable status lets a single route exercise both the silenced
        # success path and the "must still log" failure path.
        return Response("ok" if status == 200 else "fail", status_code=status)

    yield app, buf

    structlog.contextvars.clear_contextvars()
    # Detach the buffer-pointed handler so it doesn't leak into other tests.
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    _sys.stderr.flush()


def _log_lines(buf: StringIO) -> list[dict]:
    out = []
    for line in buf.getvalue().strip().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


class TestRequestContextMiddlewareNonHTTP:
    def test_non_http_scope_passes_through(self):
        """Pure-ASGI guard: non-http scopes (websocket, lifespan) bypass untouched."""
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = RequestContextMiddleware(inner_app)
        asyncio.run(middleware({"type": "websocket"}, None, None))
        assert called


class TestRequestContextMiddleware:
    def test_request_id_generated_and_echoed(self, app_and_buffer):
        app, buf = app_and_buffer
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/ok")

        assert resp.status_code == 200
        rid = resp.headers.get("x-request-id") or resp.headers.get("X-Request-ID")
        assert rid
        logs = _log_lines(buf)
        handler_log = next(ev for ev in logs if ev.get("event") == "handler_ran")
        assert handler_log["request_id"] == rid
        assert handler_log["method"] == "GET"
        assert handler_log["path"] == "/ok"
        completed = next(ev for ev in logs if ev.get("event") == "request_completed")
        assert completed["status_code"] == 200
        assert completed["request_id"] == rid

    def test_inbound_request_id_honored(self, app_and_buffer):
        app, buf = app_and_buffer
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/ok", headers={"X-Request-ID": "abc-123"})
        assert resp.headers.get("x-request-id") == "abc-123"
        logs = _log_lines(buf)
        completed = next(ev for ev in logs if ev.get("event") == "request_completed")
        assert completed["request_id"] == "abc-123"

    def test_invalid_inbound_request_id_rejected(self, app_and_buffer):
        app, buf = app_and_buffer
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/ok", headers={"X-Request-ID": "x" * 200})
        assert resp.headers.get("x-request-id") != "x" * 200

    def test_inbound_request_id_with_non_printable_rejected(self, app_and_buffer):
        app, buf = app_and_buffer
        client = TestClient(app, raise_server_exceptions=False)
        # Tab is control-range, outside printable ASCII [32, 127)
        resp = client.get("/ok", headers={"X-Request-ID": "abc\tdef"})
        assert resp.headers.get("x-request-id") != "abc\tdef"

    def test_exception_logs_request_failed(self, app_and_buffer):
        app, buf = app_and_buffer
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/boom")
        logs = _log_lines(buf)
        failed = [ev for ev in logs if ev.get("event") == "request_failed"]
        assert failed, "expected request_failed log"
        assert failed[0]["path"] == "/boom"

    def test_context_isolation_between_requests(self, app_and_buffer):
        app, buf = app_and_buffer
        client = TestClient(app, raise_server_exceptions=False)
        r1 = client.get("/ok", headers={"X-Request-ID": "first"})
        r2 = client.get("/ok", headers={"X-Request-ID": "second"})
        assert r1.headers.get("x-request-id") == "first"
        assert r2.headers.get("x-request-id") == "second"
        logs = _log_lines(buf)
        handlers = [ev for ev in logs if ev.get("event") == "handler_ran"]
        assert handlers[-1]["request_id"] == "second"
        # Between the two requests the first id must not leak into the second.
        assert handlers[-2]["request_id"] == "first"

    def test_silences_request_completed_for_health_200(self, app_and_buffer):
        """Successful /health probes must not clutter access logs."""
        app, buf = app_and_buffer
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 200
        completed = [ev for ev in _log_lines(buf) if ev.get("event") == "request_completed"]
        assert completed == []

    def test_still_logs_non_200_at_silenced_path(self, app_and_buffer):
        """A failing health probe must still log — silencing is strictly for 200s."""
        app, buf = app_and_buffer
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health?status=500")
        assert resp.status_code == 500
        completed = [ev for ev in _log_lines(buf) if ev.get("event") == "request_completed"]
        assert len(completed) == 1
        assert completed[0]["status_code"] == 500
        assert completed[0]["path"] == "/health"

    def test_still_logs_non_silenced_paths(self, app_and_buffer):
        """Regression guard — normal routes keep emitting request_completed."""
        app, buf = app_and_buffer
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/ok")
        completed = [ev for ev in _log_lines(buf) if ev.get("event") == "request_completed"]
        assert len(completed) == 1
        assert completed[0]["path"] == "/ok"

    def test_middleware_exposes_request_id_on_request_state(self, app_and_buffer):
        """The middleware must set request.state.request_id for downstream access."""
        from starlette.middleware.base import BaseHTTPMiddleware

        app, buf = app_and_buffer

        # Add a middleware that captures request.state.request_id for verification
        captured_rids = []

        class CaptureStateMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                response = await call_next(request)
                # Capture the request_id from state if it exists
                captured_rids.append(getattr(request.state, "request_id", None))
                return response

        app.add_middleware(CaptureStateMiddleware)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/ok")
        assert response.status_code == 200
        rid = response.headers.get("X-Request-ID")
        assert rid
        # The middleware should have captured the request_id from request.state
        assert len(captured_rids) > 0
        assert captured_rids[-1] == rid
