from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse, RedirectResponse

from rentivo.constants import format_month
from rentivo.db import initialize_db
from rentivo.logging import configure_logging, reconfigure
from rentivo.models import format_brl, format_brl_input
from rentivo.settings import settings
from web.auth import router as auth_router
from web.csrf import CSRFMiddleware
from web.deps import (
    AuthMiddleware,
    DBConnectionMiddleware,
    MFAEnforcementMiddleware,
    RequestServicesMiddleware,
)
from web.guards import install_guard_handlers
from web.middleware.logging import RequestContextMiddleware
from web.routes.bill import router as bill_router
from web.routes.billing import router as billing_router
from web.routes.communication import router as communication_router
from web.routes.google_auth import router as google_auth_router
from web.routes.health import router as health_router
from web.routes.invite import router as invite_router
from web.routes.organization import router as organization_router
from web.routes.password_reset import router as password_reset_router
from web.routes.security import router as security_router
from web.routes.seo import router as seo_router
from web.routes.theme import router as theme_router

configure_logging()
logger = structlog.get_logger(__name__)

BASE_DIR = Path(__file__).parent


def _build_asset_version() -> str:
    """Hash all static files to produce a short cache-bust token."""
    h = hashlib.md5()
    for f in sorted((BASE_DIR / "static").rglob("*")):
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()[:10]


ASSET_VERSION = _build_asset_version()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    initialize_db()
    # Re-apply logging config — Alembic's fileConfig may have overridden it
    reconfigure()
    logger.info("application_started")
    yield


app = FastAPI(docs_url=None, redoc_url=None, lifespan=lifespan)

install_guard_handlers(app)

app.add_middleware(DBConnectionMiddleware)
app.add_middleware(RequestServicesMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(MFAEnforcementMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.get_secret_key())
# Outermost — wraps every other middleware so logs carry request_id.
app.add_middleware(RequestContextMiddleware)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["format_brl"] = format_brl
templates.env.globals["format_brl_input"] = format_brl_input
templates.env.globals["format_month"] = format_month
templates.env.globals["asset_version"] = ASSET_VERSION
templates.env.globals["public_url"] = settings.public_url.rstrip("/") if settings.public_url else ""
templates.env.globals["gtm_container_id"] = settings.gtm_container_id
templates.env.globals["environment"] = settings.environment

app.include_router(auth_router)
app.include_router(google_auth_router)
app.include_router(billing_router)
app.include_router(bill_router)
app.include_router(communication_router)
app.include_router(organization_router)
app.include_router(invite_router)
app.include_router(password_reset_router)
app.include_router(security_router)
app.include_router(theme_router)
app.include_router(seo_router)
app.include_router(health_router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        from web.analytics import attach_to_context
        from web.csrf import get_csrf_token
        from web.flash import get_flashed_messages

        ctx = {
            "user": request.session.get("email"),
            "user_id": request.session.get("user_id"),
            "messages": get_flashed_messages(request),
            "csrf_token": get_csrf_token(request),
            "pending_invite_count": 0,
            "asset_version": ASSET_VERSION,
        }
        attach_to_context(request, "404.html", ctx)
        return templates.TemplateResponse(request, "404.html", ctx, status_code=404)
    return HTMLResponse(exc.detail or "Error", status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_exception")
    return HTMLResponse("Internal Server Error", status_code=500)


@app.get("/")
async def home(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/billings/", status_code=302)
    from web.analytics import attach_to_context

    ctx = {
        "asset_version": ASSET_VERSION,
        "user": request.session.get("email"),
    }
    attach_to_context(request, "landing.html", ctx)
    return templates.TemplateResponse(request, "landing.html", ctx)
