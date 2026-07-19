from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rentivo.api.errors import ProblemException, problem, problem_response
from rentivo.api.routes.api_keys import router as api_keys_router
from rentivo.api.routes.auth import router as auth_router
from rentivo.api.routes.billings import router as billings_router
from rentivo.api.routes.bills import router as bills_router
from rentivo.api.routes.compatibility import router as compatibility_router
from rentivo.api.routes.google_auth import router as google_auth_router
from rentivo.api.routes.health import router as health_router
from rentivo.api.routes.invites import router as invites_router
from rentivo.api.routes.mfa_auth import router as mfa_auth_router
from rentivo.api.routes.organizations import router as organizations_router
from rentivo.api.routes.profile import router as profile_router
from rentivo.api.routes.public import router as public_router
from rentivo.api.routes.security import router as security_router
from rentivo.api.routes.themes import router as themes_router
from rentivo.context import accept_inbound_request_id, new_request_id
from rentivo.db import get_engine
from rentivo.encryption.factory import get_encryption
from rentivo.logging import configure_logging, reconfigure
from rentivo.observability import configure_tracing
from rentivo.observability.middleware import TracingMiddleware
from rentivo.services.container import RequestServices
from rentivo.settings import validate_production_settings

configure_logging()
logger = structlog.get_logger(__name__)


class _LazyServices:
    def __init__(self, request: Request) -> None:
        self._request = request
        self._services: RequestServices | None = None

    def get(self) -> RequestServices:
        if self._services is None:
            self._request.state.db_conn = get_engine().connect()
            self._services = RequestServices(
                conn=self._request.state.db_conn,
                encryption=get_encryption(),
            )
        return self._services


class _RequestServicesMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        request.state.db_conn = None
        request.state.services = _LazyServices(request)
        try:
            await self.app(scope, receive, send)
        finally:
            if request.state.db_conn is not None:
                request.state.db_conn.close()


class _RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        structlog.contextvars.clear_contextvars()
        request = Request(scope, receive)
        request_id = accept_inbound_request_id(request.headers.get("X-Request-ID")) or new_request_id()
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
        )

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            structlog.contextvars.clear_contextvars()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    validate_production_settings()
    configure_tracing()
    reconfigure()
    logger.info("api_application_started")
    yield


def _validation_fields(exc: RequestValidationError) -> dict[str, str]:
    return {".".join(str(part) for part in error["loc"]): error["msg"] for error in exc.errors()}


def _http_problem(exc: StarletteHTTPException):
    if exc.status_code == 404:
        return ProblemException.not_found().problem
    detail = exc.detail if isinstance(exc.detail, str) else "A requisição não pôde ser concluída."
    return problem(
        status=exc.status_code,
        code="http_error",
        title="Erro na requisição",
        detail=detail,
    )


def create_app() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    api = APIRouter(prefix="/api/v1")
    api.include_router(health_router)
    api.include_router(auth_router)
    api.include_router(mfa_auth_router)
    api.include_router(google_auth_router)
    api.include_router(profile_router)
    api.include_router(security_router)
    api.include_router(api_keys_router)
    api.include_router(organizations_router)
    api.include_router(invites_router)
    api.include_router(billings_router)
    api.include_router(bills_router)
    api.include_router(themes_router)
    app.include_router(api)
    app.include_router(public_router)
    app.include_router(compatibility_router)

    app.add_middleware(_RequestServicesMiddleware)
    app.add_middleware(_RequestContextMiddleware)
    app.add_middleware(TracingMiddleware)

    @app.exception_handler(ProblemException)
    async def problem_exception_handler(request: Request, exc: ProblemException):
        response = problem_response(exc.problem)
        response.headers.update(exc.headers)
        if exc.problem.status == 401 and getattr(request.state, "clear_auth_cookies", False):
            from rentivo.api.authentication import ACCESS_COOKIE_NAME
            from rentivo.api.csrf import CSRF_COOKIE_NAME
            from rentivo.settings import settings

            response.delete_cookie(
                settings.access_cookie_name or ACCESS_COOKIE_NAME,
                path="/",
                secure=settings.cookie_secure,
                httponly=True,
                samesite="lax",
            )
            response.delete_cookie(
                settings.csrf_cookie_name or CSRF_COOKIE_NAME,
                path="/",
                secure=settings.cookie_secure,
                httponly=False,
                samesite="lax",
            )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return problem_response(
            problem(
                status=422,
                code="validation_error",
                title="Dados inválidos",
                detail="A requisição contém dados inválidos.",
                fields=_validation_fields(exc),
            )
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return problem_response(_http_problem(exc))

    return app
