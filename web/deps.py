from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from landlord.db import get_engine
from landlord.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyInviteRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyUserRepository,
)
from landlord.services.authorization_service import AuthorizationService
from landlord.services.bill_service import BillService
from landlord.services.billing_service import BillingService
from landlord.services.invite_service import InviteService
from landlord.services.organization_service import OrganizationService
from landlord.services.user_service import UserService
from landlord.storage.factory import get_storage
from web.flash import get_flashed_messages

logger = logging.getLogger(__name__)

PUBLIC_PATHS = {"/login", "/signup", "/static"}


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
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            await self.app(scope, receive, send)
            return
        if not request.session.get("user_id"):
            logger.info("Auth redirect: %s %s — no session", request.method, path)
            response = RedirectResponse("/login", status_code=302)
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


def _get_conn(request: Request):
    """Lazy per-request connection — created on first use, closed by middleware."""
    if request.state.db_conn is None:
        logger.debug("Creating DB connection for %s %s", request.method, request.url.path)
        request.state.db_conn = get_engine().connect()
    return request.state.db_conn


def get_billing_service(request: Request) -> BillingService:
    return BillingService(SQLAlchemyBillingRepository(_get_conn(request)))


def get_bill_service(request: Request) -> BillService:
    return BillService(SQLAlchemyBillRepository(_get_conn(request)), get_storage())


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


def render(request: Request, template_name: str, context: dict | None = None) -> Response:
    from web.app import templates
    from web.csrf import get_csrf_token

    logger.info("Rendering template: %s", template_name)
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

    response = templates.TemplateResponse(request, template_name, ctx)
    logger.info("Template rendered successfully: %s", template_name)
    return response
