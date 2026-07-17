"""Unit tests for web/guards.py.

The guards read services from ``request.state.services`` and the user from
``request.session``, so these tests exercise them through a minimal FastAPI
app with a stub middleware that injects both — no DB, no full Rentivo app.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from legacy_web.guards import (
    ACCESS_DENIED_MESSAGE,
    BILL_NOT_FOUND_MESSAGE,
    BILLING_NOT_FOUND_MESSAGE,
    ORGANIZATION_NOT_FOUND_MESSAGE,
    PIX_SETUP_REQUIRED_MESSAGE,
    BillContext,
    BillingContext,
    FlashRedirect,
    GuardJSONError,
    OrgContext,
    install_guard_handlers,
    require_bill,
    require_billing,
    require_org_admin,
    require_org_member,
)
from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.organization import Organization, OrganizationMember


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


BILLING = Billing(id=3, uuid="b-uuid", name="Apt", owner_type="user", owner_id=1)
TEST_BILL = Bill(id=9, uuid="f-uuid", billing_id=3, reference_month="2025-01")

LEVEL_TO_METHOD = {
    "view": "can_view_billing",
    "edit": "can_edit_billing",
    "delete": "can_delete_billing",
    "manage": "can_manage_bills",
    "transfer": "can_transfer_billing",
}


def _granting_services(*, role="owner", needs_pix=False):
    """Stub services where lookups succeed and every can_* check allows."""
    services = make_services()
    services.billing.get_billing_by_uuid.return_value = BILLING
    services.billing.get_billing.return_value = BILLING
    services.bill.get_bill_by_uuid.return_value = TEST_BILL
    services.pix.billing_needs_setup.return_value = needs_pix
    services.authorization.get_role_for_billing.return_value = role
    for method in LEVEL_TO_METHOD.values():
        getattr(services.authorization, method).return_value = True
    return services


def _billing_app(services, session, *, level="view", pix=False, json=False):
    app = FastAPI()

    @app.get("/billings/{billing_uuid}/probe")
    async def probe(ctx: BillingContext = Depends(require_billing(level, pix=pix, json=json))):
        return {"uuid": ctx.billing.uuid, "role": ctx.role, "user_id": ctx.user_id}

    return finalize_app(app, services, session)


def _bill_app(services, session, *, level="view", pix=False, json=False):
    app = FastAPI()

    @app.get("/billings/{billing_uuid}/bills/{bill_uuid}/probe")
    async def probe(ctx: BillContext = Depends(require_bill(level, pix=pix, json=json))):
        return {
            "bill_uuid": ctx.bill.uuid,
            "billing_uuid": ctx.billing.uuid,
            "role": ctx.role,
            "user_id": ctx.user_id,
        }

    return finalize_app(app, services, session)


class TestLevelValidation:
    def test_require_billing_rejects_unknown_level(self):
        with pytest.raises(ValueError, match="Unknown authorization level"):
            require_billing("superuser")

    def test_require_bill_rejects_unknown_level(self):
        with pytest.raises(ValueError, match="Unknown authorization level"):
            require_bill("root")


class TestRequireBilling:
    @pytest.mark.parametrize(("level", "method"), sorted(LEVEL_TO_METHOD.items()))
    def test_level_maps_to_authorization_method(self, level, method):
        services = _granting_services()
        client = _billing_app(services, {"user_id": 1}, level=level)
        response = client.get("/billings/b-uuid/probe")
        assert response.status_code == 200
        assert response.json() == {"uuid": "b-uuid", "role": "owner", "user_id": 1}
        getattr(services.authorization, method).assert_called_once_with(1, BILLING)

    def test_billing_not_found_flash(self):
        services = _granting_services()
        services.billing.get_billing_by_uuid.return_value = None
        session = {"user_id": 1}
        client = _billing_app(services, session)
        response = client.get("/billings/b-uuid/probe", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/"
        assert session["_messages"] == [{"message": BILLING_NOT_FOUND_MESSAGE, "category": "danger"}]

    def test_billing_not_found_json(self):
        services = _granting_services()
        services.billing.get_billing_by_uuid.return_value = None
        client = _billing_app(services, {"user_id": 1}, json=True)
        response = client.get("/billings/b-uuid/probe")
        assert response.status_code == 404
        assert response.json() == {"error": BILLING_NOT_FOUND_MESSAGE}

    def test_denied_flash(self):
        services = _granting_services()
        services.authorization.can_view_billing.return_value = False
        session = {"user_id": 1}
        client = _billing_app(services, session)
        response = client.get("/billings/b-uuid/probe", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/"
        assert session["_messages"] == [{"message": ACCESS_DENIED_MESSAGE, "category": "danger"}]

    def test_denied_json(self):
        services = _granting_services()
        services.authorization.can_view_billing.return_value = False
        client = _billing_app(services, {"user_id": 1}, json=True)
        response = client.get("/billings/b-uuid/probe")
        assert response.status_code == 403
        assert response.json() == {"error": ACCESS_DENIED_MESSAGE}

    def test_pix_gate_flash(self):
        services = _granting_services(needs_pix=True)
        session = {"user_id": 1}
        client = _billing_app(services, session, level="manage", pix=True)
        response = client.get("/billings/b-uuid/probe", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/billings/b-uuid"
        assert session["_messages"] == [{"message": PIX_SETUP_REQUIRED_MESSAGE, "category": "warning"}]

    def test_pix_gate_json(self):
        services = _granting_services(needs_pix=True)
        client = _billing_app(services, {"user_id": 1}, level="manage", pix=True, json=True)
        response = client.get("/billings/b-uuid/probe")
        assert response.status_code == 400
        assert response.json() == {"error": PIX_SETUP_REQUIRED_MESSAGE}

    def test_pix_configured_passes_gate(self):
        services = _granting_services(needs_pix=False)
        client = _billing_app(services, {"user_id": 1}, level="manage", pix=True)
        response = client.get("/billings/b-uuid/probe")
        assert response.status_code == 200
        services.pix.billing_needs_setup.assert_called_once_with(BILLING)

    def test_pix_not_consulted_when_disabled(self):
        services = _granting_services(needs_pix=True)
        client = _billing_app(services, {"user_id": 1})
        response = client.get("/billings/b-uuid/probe")
        assert response.status_code == 200
        services.pix.billing_needs_setup.assert_not_called()

    def test_role_defaults_to_empty_string(self):
        services = _granting_services(role=None)
        client = _billing_app(services, {"user_id": 1})
        response = client.get("/billings/b-uuid/probe")
        assert response.status_code == 200
        assert response.json()["role"] == ""


class TestRequireBill:
    def test_success(self):
        services = _granting_services(role="manager")
        client = _bill_app(services, {"user_id": 1}, level="manage")
        response = client.get("/billings/b-uuid/bills/f-uuid/probe")
        assert response.status_code == 200
        assert response.json() == {
            "bill_uuid": "f-uuid",
            "billing_uuid": "b-uuid",
            "role": "manager",
            "user_id": 1,
        }
        services.bill.get_bill_by_uuid.assert_called_once_with("f-uuid")
        services.billing.get_billing.assert_called_once_with(3)
        services.authorization.can_manage_bills.assert_called_once_with(1, BILLING)

    def test_bill_not_found_flash(self):
        services = _granting_services()
        services.bill.get_bill_by_uuid.return_value = None
        session = {"user_id": 1}
        client = _bill_app(services, session)
        response = client.get("/billings/b-uuid/bills/f-uuid/probe", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/"
        assert session["_messages"] == [{"message": BILL_NOT_FOUND_MESSAGE, "category": "danger"}]

    def test_bill_not_found_json(self):
        services = _granting_services()
        services.bill.get_bill_by_uuid.return_value = None
        client = _bill_app(services, {"user_id": 1}, json=True)
        response = client.get("/billings/b-uuid/bills/f-uuid/probe")
        assert response.status_code == 404
        assert response.json() == {"error": BILL_NOT_FOUND_MESSAGE}

    def test_billing_missing_flash(self):
        services = _granting_services()
        services.billing.get_billing.return_value = None
        session = {"user_id": 1}
        client = _bill_app(services, session)
        response = client.get("/billings/b-uuid/bills/f-uuid/probe", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/"
        assert session["_messages"] == [{"message": BILLING_NOT_FOUND_MESSAGE, "category": "danger"}]

    def test_billing_uuid_mismatch_flash(self):
        services = _granting_services()
        session = {"user_id": 1}
        client = _bill_app(services, session)
        response = client.get("/billings/SOMEONE-ELSES-UUID/bills/f-uuid/probe", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/"
        assert session["_messages"] == [{"message": BILLING_NOT_FOUND_MESSAGE, "category": "danger"}]

    def test_billing_uuid_mismatch_json(self):
        services = _granting_services()
        client = _bill_app(services, {"user_id": 1}, json=True)
        response = client.get("/billings/SOMEONE-ELSES-UUID/bills/f-uuid/probe")
        assert response.status_code == 404
        assert response.json() == {"error": BILLING_NOT_FOUND_MESSAGE}

    def test_denied_flash(self):
        services = _granting_services()
        services.authorization.can_view_billing.return_value = False
        session = {"user_id": 1}
        client = _bill_app(services, session)
        response = client.get("/billings/b-uuid/bills/f-uuid/probe", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/"
        assert session["_messages"] == [{"message": ACCESS_DENIED_MESSAGE, "category": "danger"}]

    def test_denied_json(self):
        services = _granting_services()
        services.authorization.can_view_billing.return_value = False
        client = _bill_app(services, {"user_id": 1}, json=True)
        response = client.get("/billings/b-uuid/bills/f-uuid/probe")
        assert response.status_code == 403
        assert response.json() == {"error": ACCESS_DENIED_MESSAGE}

    def test_pix_gate_flash(self):
        services = _granting_services(needs_pix=True)
        session = {"user_id": 1}
        client = _bill_app(services, session, level="manage", pix=True)
        response = client.get("/billings/b-uuid/bills/f-uuid/probe", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/billings/b-uuid"
        assert session["_messages"] == [{"message": PIX_SETUP_REQUIRED_MESSAGE, "category": "warning"}]

    def test_pix_gate_json(self):
        services = _granting_services(needs_pix=True)
        client = _bill_app(services, {"user_id": 1}, level="manage", pix=True, json=True)
        response = client.get("/billings/b-uuid/bills/f-uuid/probe")
        assert response.status_code == 400
        assert response.json() == {"error": PIX_SETUP_REQUIRED_MESSAGE}
