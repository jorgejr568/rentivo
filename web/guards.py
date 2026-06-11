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
