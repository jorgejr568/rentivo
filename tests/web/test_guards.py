"""Unit tests for web/guards.py.

The guards read services from ``request.state.services`` and the user from
``request.session``, so these tests exercise them through a minimal FastAPI
app with a stub middleware that injects both — no DB, no full Rentivo app.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from starlette.testclient import TestClient

from web.guards import (
    FlashRedirect,
    GuardJSONError,
    install_guard_handlers,
)


class StubContextMiddleware:
    """Injects a stub services container and a plain-dict session into the scope.

    ``request.state`` is backed by ``scope["state"]`` and ``request.session`` by
    ``scope["session"]``, so setting both here is all the guards need. The
    session dict is shared with the test so flashed messages can be asserted.
    """

    def __init__(self, app, services, session):
        self.app = app
        self.services = services
        self.session = session

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["services"] = self.services
            scope["session"] = self.session
        await self.app(scope, receive, send)


def make_services(**overrides):
    services = SimpleNamespace(
        organization=MagicMock(),
        authorization=MagicMock(),
        billing=MagicMock(),
        bill=MagicMock(),
        pix=MagicMock(),
    )
    for name, value in overrides.items():
        setattr(services, name, value)
    return services


def finalize_app(app: FastAPI, services, session) -> TestClient:
    """Install the guard exception handlers and the stub middleware."""
    install_guard_handlers(app)
    app.add_middleware(StubContextMiddleware, services=services, session=session)
    return TestClient(app)


class TestGuardExceptions:
    def test_flash_redirect_defaults_to_danger(self):
        exc = FlashRedirect("msg", "/url")
        assert exc.message == "msg"
        assert exc.url == "/url"
        assert exc.category == "danger"
        assert str(exc) == "msg"

    def test_flash_redirect_custom_category(self):
        exc = FlashRedirect("msg", "/url", category="warning")
        assert exc.category == "warning"

    def test_guard_json_error(self):
        exc = GuardJSONError("nope", 403)
        assert exc.message == "nope"
        assert exc.status_code == 403
        assert str(exc) == "nope"


def _exception_app():
    app = FastAPI()

    @app.get("/flash")
    async def flash_route():
        raise FlashRedirect("Mensagem.", "/destino", category="warning")

    @app.get("/json")
    async def json_route():
        raise GuardJSONError("Erro.", 418)

    session: dict = {}
    client = finalize_app(app, make_services(), session)
    return client, session


class TestGuardExceptionHandlers:
    def test_flash_redirect_handler_flashes_and_redirects(self):
        client, session = _exception_app()
        response = client.get("/flash", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/destino"
        assert session["_messages"] == [{"message": "Mensagem.", "category": "warning"}]

    def test_guard_json_error_handler_returns_json(self):
        client, _ = _exception_app()
        response = client.get("/json")
        assert response.status_code == 418
        assert response.json() == {"error": "Erro."}
