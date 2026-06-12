"""Reusable FastAPI guard dependencies for the web layer.

Each guard resolves an entity from its path parameter, authorizes the
session user, and either returns a frozen context object for the handler
or raises :class:`FlashRedirect` (HTML routes) / :class:`GuardJSONError`
(JSON routes). The app-level exception handlers installed by
:func:`install_guard_handlers` convert those exceptions into the
flash + 302 / ``{"error": ...}`` responses the routes used to build inline.

Guards read services via ``request.state.services`` (the lazy proxy from
``web/deps.py``) and the user via ``request.session["user_id"]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.organization import Organization, OrganizationMember
from web.flash import flash

logger = structlog.get_logger(__name__)

# Canonical user-facing messages (PT-BR).
ORGANIZATION_NOT_FOUND_MESSAGE = "Organização não encontrada."
BILLING_NOT_FOUND_MESSAGE = "Cobrança não encontrada."
BILL_NOT_FOUND_MESSAGE = "Fatura não encontrada."
ACCESS_DENIED_MESSAGE = "Acesso negado."
PIX_SETUP_REQUIRED_MESSAGE = "Configure a chave PIX, o nome e a cidade do recebedor antes de continuar."


class FlashRedirect(Exception):
    """Guard failure for HTML routes — converted to flash + 302 by the app handler."""

    def __init__(self, message: str, url: str, category: str = "danger") -> None:
        super().__init__(message)
        self.message = message
        self.url = url
        self.category = category


class GuardJSONError(Exception):
    """Guard failure for JSON routes — converted to ``{"error": message}`` + status."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class OrgContext:
    org: Organization
    member: OrganizationMember
    user_id: int


@dataclass(frozen=True)
class BillingContext:
    billing: Billing
    role: str
    user_id: int


@dataclass(frozen=True)
class BillContext:
    bill: Bill
    billing: Billing
    role: str
    user_id: int


async def flash_redirect_handler(request: Request, exc: FlashRedirect) -> RedirectResponse:
    flash(request, exc.message, exc.category)
    return RedirectResponse(exc.url, status_code=302)


async def guard_json_error_handler(request: Request, exc: GuardJSONError) -> JSONResponse:
    return JSONResponse({"error": exc.message}, status_code=exc.status_code)


def install_guard_handlers(app: FastAPI) -> None:
    """Register the guard exception handlers on ``app``."""
    app.add_exception_handler(FlashRedirect, flash_redirect_handler)
    app.add_exception_handler(GuardJSONError, guard_json_error_handler)


def _resolve_org(request: Request, org_uuid: str) -> Organization:
    org = request.state.services.organization.get_by_uuid(org_uuid)
    if not org:
        logger.warning("organization_not_found", org_uuid=org_uuid, path=request.url.path)
        raise FlashRedirect(ORGANIZATION_NOT_FOUND_MESSAGE, "/organizations/")
    return org


async def require_org_member(org_uuid: str, request: Request) -> OrgContext:
    """Resolve the org and require the session user to be a member of it."""
    org = _resolve_org(request, org_uuid)
    user_id = request.session.get("user_id")
    member = request.state.services.organization.get_member(org.id, user_id)
    if member is None:
        logger.warning("organization_access_denied", org_uuid=org_uuid, path=request.url.path)
        raise FlashRedirect(ACCESS_DENIED_MESSAGE, "/organizations/")
    return OrgContext(org=org, member=member, user_id=user_id)


async def require_org_admin(org_uuid: str, request: Request) -> OrgContext:
    """Resolve the org and require the session user to be an admin of it."""
    org = _resolve_org(request, org_uuid)
    user_id = request.session.get("user_id")
    member = request.state.services.organization.get_member(org.id, user_id)
    if member is None or not request.state.services.authorization.can_admin_org(user_id, org.id):
        logger.warning("organization_admin_access_denied", org_uuid=org_uuid, path=request.url.path)
        raise FlashRedirect(ACCESS_DENIED_MESSAGE, f"/organizations/{org_uuid}")
    return OrgContext(org=org, member=member, user_id=user_id)


_LEVEL_METHODS = {
    "view": "can_view_billing",
    "edit": "can_edit_billing",
    "delete": "can_delete_billing",
    "manage": "can_manage_bills",
    "transfer": "can_transfer_billing",
}


def _level_method(level: str) -> str:
    try:
        return _LEVEL_METHODS[level]
    except KeyError:
        raise ValueError(f"Unknown authorization level: {level!r}") from None


def _fail(message: str, url: str, status_code: int, *, json: bool, category: str = "danger") -> NoReturn:
    if json:
        raise GuardJSONError(message, status_code)
    raise FlashRedirect(message, url, category)


def _check_pix_complete(request: Request, billing: Billing, *, json: bool) -> None:
    """Raise the canonical PIX-setup failure if the billing's PIX is incomplete."""
    if request.state.services.pix.billing_needs_setup(billing):
        logger.warning("pix_setup_required", billing_uuid=billing.uuid, path=request.url.path)
        _fail(PIX_SETUP_REQUIRED_MESSAGE, f"/billings/{billing.uuid}", 400, json=json, category="warning")


def require_billing(level: str, *, pix: bool = False, json: bool = False):
    """Dependency factory: resolve the billing by ``billing_uuid`` and authorize ``level``.

    With ``pix=True`` additionally requires the billing's PIX setup to be
    complete. With ``json=True`` failures raise :class:`GuardJSONError`
    instead of :class:`FlashRedirect`.
    """
    method_name = _level_method(level)

    async def dependency(billing_uuid: str, request: Request) -> BillingContext:
        services = request.state.services
        billing = services.billing.get_billing_by_uuid(billing_uuid)
        if not billing:
            logger.warning("billing_not_found", billing_uuid=billing_uuid, path=request.url.path)
            _fail(BILLING_NOT_FOUND_MESSAGE, "/", 404, json=json)
        user_id = request.session.get("user_id")
        auth = services.authorization
        if not getattr(auth, method_name)(user_id, billing):
            logger.warning("billing_access_denied", billing_uuid=billing_uuid, level=level, path=request.url.path)
            _fail(ACCESS_DENIED_MESSAGE, "/", 403, json=json)
        if pix:
            _check_pix_complete(request, billing, json=json)
        role = auth.get_role_for_billing(user_id, billing) or ""
        return BillingContext(billing=billing, role=role, user_id=user_id)

    return dependency


def require_bill(level: str, *, pix: bool = False, json: bool = False):
    """Dependency factory: resolve the bill by ``bill_uuid``, its billing, and authorize ``level``.

    Owns the ``billing.uuid == billing_uuid`` cross-check: a URL pairing a
    bill with an unrelated billing's uuid fails as "billing not found".
    """
    method_name = _level_method(level)

    async def dependency(billing_uuid: str, bill_uuid: str, request: Request) -> BillContext:
        services = request.state.services
        bill = services.bill.get_bill_by_uuid(bill_uuid)
        if not bill:
            logger.warning("bill_not_found", bill_uuid=bill_uuid, path=request.url.path)
            _fail(BILL_NOT_FOUND_MESSAGE, "/", 404, json=json)
        billing = services.billing.get_billing(bill.billing_id)
        if not billing or billing.uuid != billing_uuid:
            logger.warning(
                "billing_not_found_for_bill",
                billing_id=bill.billing_id,
                bill_uuid=bill_uuid,
                path=request.url.path,
            )
            _fail(BILLING_NOT_FOUND_MESSAGE, "/", 404, json=json)
        user_id = request.session.get("user_id")
        auth = services.authorization
        if not getattr(auth, method_name)(user_id, billing):
            logger.warning("bill_access_denied", bill_uuid=bill_uuid, level=level, path=request.url.path)
            _fail(ACCESS_DENIED_MESSAGE, "/", 403, json=json)
        if pix:
            _check_pix_complete(request, billing, json=json)
        role = auth.get_role_for_billing(user_id, billing) or ""
        return BillContext(bill=bill, billing=billing, role=role, user_id=user_id)

    return dependency
