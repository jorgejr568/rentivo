from __future__ import annotations

import hashlib
import logging
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse, RedirectResponse

from rentivo.constants import format_month
from rentivo.db import initialize_db
from rentivo.logging import configure_logging, reconfigure
from rentivo.models import format_brl
from rentivo.settings import settings
from web.auth import router as auth_router
from web.csrf import CSRFMiddleware
from web.deps import AuthMiddleware, DBConnectionMiddleware, MFAEnforcementMiddleware
from web.routes.bill import router as bill_router
from web.routes.billing import router as billing_router
from web.routes.invite import router as invite_router
from web.routes.organization import router as organization_router
from web.routes.security import router as security_router

configure_logging()
logger = logging.getLogger(__name__)

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
    logger.info("Application started")
    yield


app = FastAPI(docs_url=None, redoc_url=None, lifespan=lifespan)

app.add_middleware(DBConnectionMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(MFAEnforcementMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.get_secret_key())

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["format_brl"] = format_brl
templates.env.globals["format_month"] = format_month
templates.env.globals["asset_version"] = ASSET_VERSION

app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(bill_router)
app.include_router(organization_router)
app.include_router(invite_router)
app.include_router(security_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception on %s %s:\n%s",
        request.method,
        request.url.path,
        traceback.format_exc(),
    )
    return HTMLResponse("Internal Server Error", status_code=500)


@app.get("/")
async def home(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/billings/", status_code=302)
    return templates.TemplateResponse(
        request,
        "landing.html",
        {
            "asset_version": ASSET_VERSION,
            "user": request.session.get("username"),
        },
    )
