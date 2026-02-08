from __future__ import annotations

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

PUBLIC_PATHS = {"/login", "/static"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)
        if not request.session.get("user"):
            return RedirectResponse("/login", status_code=302)
        return await call_next(request)


def _connect():
    """Fresh connection per call — avoids stale transactions in long-running server."""
    return get_engine().connect()


def get_billing_service() -> BillingService:
    return BillingService(SQLAlchemyBillingRepository(_connect()))


def get_bill_service() -> BillService:
    return BillService(SQLAlchemyBillRepository(_connect()), get_storage())


def get_user_service() -> UserService:
    return UserService(SQLAlchemyUserRepository(_connect()))


def render(request: Request, template_name: str, context: dict | None = None) -> Response:
    from web.app import templates

    ctx = context or {}
    ctx["request"] = request
    ctx["user"] = request.session.get("user")
    ctx["messages"] = get_flashed_messages(request)
    return templates.TemplateResponse(request, template_name, ctx)
