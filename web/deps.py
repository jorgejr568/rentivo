from __future__ import annotations

import logging
from functools import cache

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from rentivo.db import get_engine
from rentivo.services.audit_service import AuditService
from rentivo.services.authorization_service import AuthorizationService
from rentivo.services.bill_service import BillService
from rentivo.services.billing_service import BillingService
from rentivo.services.invite_service import InviteService
from rentivo.services.mfa_service import MFAService
from rentivo.services.organization_service import OrganizationService
from rentivo.services.theme_service import ThemeService
from rentivo.services.user_service import UserService
from rentivo.storage.factory import get_storage
from web.flash import get_flashed_messages
from web.request_scope import close_request_scope, count_pending_invites_for_user, get_request_services

logger = logging.getLogger(__name__)

PUBLIC_PREFIX_PATHS = {"/login", "/signup", "/static", "/mfa-verify", "/security/passkeys/auth"}
PUBLIC_EXACT_PATHS = {"/"}

# Paths that MFA-enforcement redirect allows even when mfa_setup_required is set
MFA_EXEMPT_PREFIXES = {"/security", "/logout", "/login", "/signup", "/static", "/mfa-verify"}
MFA_EXEMPT_EXACT = {"/"}


@cache
def _get_route_prefixes(app: ASGIApp) -> frozenset[str]:
    """Extract first path segments from registered routes (cached at startup)."""
    return frozenset(
        segment
        for route in getattr(app, "routes", ())
        if (segment := getattr(route, "path", "").strip("/").split("/")[0])
    )


def _path_matches_route(scope: Scope) -> bool:
    """O(1) check whether the request path could match a registered route."""
    app = scope.get("app")
    if not app:
        return True
    first_segment = scope.get("path", "").strip("/").split("/")[0]
    return first_segment in _get_route_prefixes(app)


class AuthMiddleware:
    """Pure ASGI middleware for authentication checks."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path
        if path in PUBLIC_EXACT_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIX_PATHS):
            await self.app(scope, receive, send)
            return
        if not request.session.get("user_id"):
            if not _path_matches_route(scope):
                await self.app(scope, receive, send)
                return

            logger.info("Auth redirect: %s %s — no session", request.method, path)
            response = RedirectResponse("/login", status_code=302)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class MFAEnforcementMiddleware:
    """Pure ASGI middleware — forces users in MFA-enforcing orgs to set up MFA."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        # Skip for public/exempt paths
        if path in MFA_EXEMPT_EXACT or any(path.startswith(p) for p in MFA_EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        user_id = request.session.get("user_id")
        if not user_id:
            await self.app(scope, receive, send)
            return

        if request.session.get("mfa_setup_required"):
            logger.info("MFA enforcement redirect: %s %s — user=%s", request.method, path, user_id)
            response = RedirectResponse("/security/totp/setup", status_code=302)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class DBConnectionMiddleware:
    """Pure ASGI middleware — manages request-scoped DB/services cleanup."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        try:
            await self.app(scope, receive, send)
        finally:
            close_request_scope(request)


def _request_services(request: Request):
    return get_request_services(request, engine_factory=get_engine, storage_factory=get_storage)


def _pending_invite_count(request: Request, user_id: int) -> int:
    return count_pending_invites_for_user(
        request,
        user_id,
        engine_factory=get_engine,
        storage_factory=get_storage,
    )


def get_billing_service(request: Request) -> BillingService:
    return _request_services(request).billing_service


def get_bill_service(request: Request) -> BillService:
    return _request_services(request).bill_service


def get_theme_service(request: Request) -> ThemeService:
    return _request_services(request).theme_service


def get_user_service(request: Request) -> UserService:
    return _request_services(request).user_service


def get_organization_service(request: Request) -> OrganizationService:
    return _request_services(request).organization_service


def get_invite_service(request: Request) -> InviteService:
    return _request_services(request).invite_service


def get_authorization_service(request: Request) -> AuthorizationService:
    return _request_services(request).authorization_service


def get_audit_service(request: Request) -> AuditService:
    return _request_services(request).audit_service


def get_mfa_service(request: Request) -> MFAService:
    return _request_services(request).mfa_service


def render(request: Request, template_name: str, context: dict | None = None) -> Response:
    from web.app import templates
    from web.csrf import get_csrf_token

    logger.debug("Rendering %s", template_name)
    ctx = context or {}
    ctx["request"] = request
    ctx["user"] = request.session.get("username")
    ctx["user_id"] = request.session.get("user_id")
    ctx["messages"] = get_flashed_messages(request)
    ctx["csrf_token"] = get_csrf_token(request)

    user_id = request.session.get("user_id")
    if user_id and "pending_invite_count" not in ctx:
        try:
            ctx["pending_invite_count"] = _pending_invite_count(request, user_id)
        except Exception:
            ctx["pending_invite_count"] = 0
    else:
        ctx.setdefault("pending_invite_count", 0)

    return templates.TemplateResponse(request, template_name, ctx)
