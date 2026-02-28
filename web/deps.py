from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from rentivo.db import get_engine
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyAuditLogRepository,
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyInviteRepository,
    SQLAlchemyMFATOTPRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyPasskeyRepository,
    SQLAlchemyReceiptRepository,
    SQLAlchemyRecoveryCodeRepository,
    SQLAlchemyUserRepository,
)
from rentivo.services.audit_service import AuditService
from rentivo.services.authorization_service import AuthorizationService
from rentivo.services.bill_service import BillService
from rentivo.services.billing_service import BillingService
from rentivo.services.invite_service import InviteService
from rentivo.services.mfa_service import MFAService
from rentivo.services.organization_service import OrganizationService
from rentivo.services.user_service import UserService
from rentivo.storage.factory import get_storage
from web.flash import get_flashed_messages

logger = logging.getLogger(__name__)

PUBLIC_PREFIX_PATHS = {"/login", "/signup", "/static", "/mfa-verify", "/security/passkeys/auth"}
PUBLIC_EXACT_PATHS = {"/"}

# Paths that MFA-enforcement redirect allows even when mfa_setup_required is set
MFA_EXEMPT_PREFIXES = {"/security", "/logout", "/login", "/signup", "/static", "/mfa-verify"}
MFA_EXEMPT_EXACT = {"/"}


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
    """Pure ASGI middleware — creates a single DB connection per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request.state.db_conn = None
        try:
            await self.app(scope, receive, send)
        finally:
            conn = getattr(request.state, "db_conn", None)
            if conn is not None:
                conn.close()
                logger.debug("DB connection closed for %s %s", request.method, request.url.path)


def _get_conn(request: Request):
    """Lazy per-request connection — created on first use, closed by middleware."""
    if request.state.db_conn is None:
        logger.debug("Creating DB connection for %s %s", request.method, request.url.path)
        request.state.db_conn = get_engine().connect()
    return request.state.db_conn


def get_billing_service(request: Request) -> BillingService:
    return BillingService(SQLAlchemyBillingRepository(_get_conn(request)))


def get_bill_service(request: Request) -> BillService:
    conn = _get_conn(request)
    return BillService(
        SQLAlchemyBillRepository(conn),
        get_storage(),
        SQLAlchemyReceiptRepository(conn),
    )


def get_user_service(request: Request) -> UserService:
    return UserService(SQLAlchemyUserRepository(_get_conn(request)))


def get_organization_service(request: Request) -> OrganizationService:
    return OrganizationService(SQLAlchemyOrganizationRepository(_get_conn(request)))


def get_invite_service(request: Request) -> InviteService:
    conn = _get_conn(request)
    return InviteService(
        SQLAlchemyInviteRepository(conn),
        SQLAlchemyOrganizationRepository(conn),
        SQLAlchemyUserRepository(conn),
    )


def get_authorization_service(request: Request) -> AuthorizationService:
    return AuthorizationService(SQLAlchemyOrganizationRepository(_get_conn(request)))


def get_audit_service(request: Request) -> AuditService:
    return AuditService(SQLAlchemyAuditLogRepository(_get_conn(request)))


def get_mfa_service(request: Request) -> MFAService:
    conn = _get_conn(request)
    return MFAService(
        SQLAlchemyMFATOTPRepository(conn),
        SQLAlchemyRecoveryCodeRepository(conn),
        SQLAlchemyPasskeyRepository(conn),
        SQLAlchemyOrganizationRepository(conn),
    )


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
            conn = _get_conn(request)
            invite_repo = SQLAlchemyInviteRepository(conn)
            ctx["pending_invite_count"] = invite_repo.count_pending_for_user(user_id)
        except Exception:
            ctx["pending_invite_count"] = 0
    else:
        ctx.setdefault("pending_invite_count", 0)

    return templates.TemplateResponse(request, template_name, ctx)
