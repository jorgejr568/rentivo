"""Unit tests for web/guards.py.

The guards read services from ``request.state.services`` and the user from
``request.session``, so these tests exercise them through a minimal FastAPI
app with a stub middleware that injects both — no DB, no full Rentivo app.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from rentivo.models.organization import Organization, OrganizationMember
from web.guards import (
    ACCESS_DENIED_MESSAGE,
    ORGANIZATION_NOT_FOUND_MESSAGE,
    FlashRedirect,
    GuardJSONError,
    OrgContext,
    install_guard_handlers,
    require_org_admin,
    require_org_member,
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


ORG = Organization(id=7, uuid="org-uuid", name="Acme")


def _org_member(role="viewer"):
    return OrganizationMember(organization_id=7, user_id=1, role=role)


def _org_app(services, session):
    app = FastAPI()

    @app.get("/orgs/{org_uuid}/member")
    async def member_route(ctx: OrgContext = Depends(require_org_member)):
        return {"org_id": ctx.org.id, "role": ctx.member.role, "user_id": ctx.user_id}

    @app.get("/orgs/{org_uuid}/admin")
    async def admin_route(ctx: OrgContext = Depends(require_org_admin)):
        return {"org_id": ctx.org.id, "role": ctx.member.role, "user_id": ctx.user_id}

    return finalize_app(app, services, session)


class TestRequireOrgMember:
    def test_success(self):
        services = make_services()
        services.organization.get_by_uuid.return_value = ORG
        services.organization.get_member.return_value = _org_member()
        client = _org_app(services, {"user_id": 1})
        response = client.get("/orgs/org-uuid/member")
        assert response.status_code == 200
        assert response.json() == {"org_id": 7, "role": "viewer", "user_id": 1}
        services.organization.get_by_uuid.assert_called_once_with("org-uuid")
        services.organization.get_member.assert_called_once_with(7, 1)

    def test_org_not_found(self):
        services = make_services()
        services.organization.get_by_uuid.return_value = None
        session = {"user_id": 1}
        client = _org_app(services, session)
        response = client.get("/orgs/org-uuid/member", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/organizations/"
        assert session["_messages"] == [{"message": ORGANIZATION_NOT_FOUND_MESSAGE, "category": "danger"}]

    def test_not_a_member(self):
        services = make_services()
        services.organization.get_by_uuid.return_value = ORG
        services.organization.get_member.return_value = None
        session = {"user_id": 1}
        client = _org_app(services, session)
        response = client.get("/orgs/org-uuid/member", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/organizations/"
        assert session["_messages"] == [{"message": ACCESS_DENIED_MESSAGE, "category": "danger"}]


class TestRequireOrgAdmin:
    def test_success(self):
        services = make_services()
        services.organization.get_by_uuid.return_value = ORG
        services.organization.get_member.return_value = _org_member(role="admin")
        services.authorization.can_admin_org.return_value = True
        client = _org_app(services, {"user_id": 1})
        response = client.get("/orgs/org-uuid/admin")
        assert response.status_code == 200
        assert response.json() == {"org_id": 7, "role": "admin", "user_id": 1}
        services.authorization.can_admin_org.assert_called_once_with(1, 7)

    def test_org_not_found(self):
        services = make_services()
        services.organization.get_by_uuid.return_value = None
        session = {"user_id": 1}
        client = _org_app(services, session)
        response = client.get("/orgs/org-uuid/admin", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/organizations/"
        assert session["_messages"] == [{"message": ORGANIZATION_NOT_FOUND_MESSAGE, "category": "danger"}]

    def test_non_member_denied_without_admin_check(self):
        services = make_services()
        services.organization.get_by_uuid.return_value = ORG
        services.organization.get_member.return_value = None
        session = {"user_id": 1}
        client = _org_app(services, session)
        response = client.get("/orgs/org-uuid/admin", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/organizations/org-uuid"
        assert session["_messages"] == [{"message": ACCESS_DENIED_MESSAGE, "category": "danger"}]
        services.authorization.can_admin_org.assert_not_called()

    def test_member_not_admin(self):
        services = make_services()
        services.organization.get_by_uuid.return_value = ORG
        services.organization.get_member.return_value = _org_member(role="viewer")
        services.authorization.can_admin_org.return_value = False
        session = {"user_id": 1}
        client = _org_app(services, session)
        response = client.get("/orgs/org-uuid/admin", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/organizations/org-uuid"
        assert session["_messages"] == [{"message": ACCESS_DENIED_MESSAGE, "category": "danger"}]
