from __future__ import annotations

from functools import lru_cache

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from landlord.repositories.factory import (
    get_bill_repository,
    get_billing_repository,
    get_user_repository,
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


def get_billing_service() -> BillingService:
    return BillingService(get_billing_repository())


def get_bill_service() -> BillService:
    return BillService(get_bill_repository(), get_storage())


def get_user_service() -> UserService:
    return UserService(get_user_repository())


def render(request: Request, template_name: str, context: dict | None = None) -> Response:
    from web.app import templates

    ctx = context or {}
    ctx["request"] = request
    ctx["user"] = request.session.get("user")
    ctx["messages"] = get_flashed_messages(request)
    return templates.TemplateResponse(request, template_name, ctx)
