from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from landlord.db import get_engine
from landlord.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyUserRepository,
)
from landlord.services.bill_service import BillService
from landlord.services.billing_service import BillingService
from landlord.services.user_service import UserService
from landlord.storage.factory import get_storage
from web.flash import get_flashed_messages

logger = logging.getLogger(__name__)

PUBLIC_PATHS = {"/login", "/static"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)
        if not request.session.get("user"):
            logger.info("Auth redirect: %s %s — no session", request.method, path)
            return RedirectResponse("/login", status_code=302)
        return await call_next(request)


class DBConnectionMiddleware(BaseHTTPMiddleware):
    """Creates a single DB connection per request and closes it when done."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request.state.db_conn = None
        try:
            response = await call_next(request)
            return response
        except Exception:
            logger.exception(
                "Exception in %s %s", request.method, request.url.path,
            )
            raise
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


def render(request: Request, template_name: str, context: dict | None = None) -> Response:
    from web.app import templates
    from web.csrf import get_csrf_token

    logger.info("Rendering template: %s", template_name)
    ctx = context or {}
    ctx["request"] = request
    ctx["user"] = request.session.get("user")
    ctx["messages"] = get_flashed_messages(request)
    ctx["csrf_token"] = get_csrf_token(request)
    response = templates.TemplateResponse(request, template_name, ctx)
    logger.info("Template rendered successfully: %s", template_name)
    return response
