from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from landlord.constants import format_month
from landlord.db import initialize_db
from landlord.models import format_brl
from landlord.settings import settings
from web.auth import router as auth_router
from web.deps import AuthMiddleware, DBConnectionMiddleware
from web.routes.bill import router as bill_router
from web.routes.billing import router as billing_router

BASE_DIR = Path(__file__).parent

app = FastAPI(docs_url=None, redoc_url=None)

app.add_middleware(DBConnectionMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["format_brl"] = format_brl
templates.env.globals["format_month"] = format_month

app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(bill_router)


@app.get("/")
async def home(request: Request):
    return RedirectResponse("/billings/", status_code=302)


@app.on_event("startup")
async def startup():
    initialize_db()
