from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from ulid import ULID

from rentivo.api.errors import ProblemException, problem, problem_response
from rentivo.api.routes.health import router as health_router
from rentivo.db import get_engine, initialize_db
from rentivo.encryption.factory import get_encryption
from rentivo.logging import configure_logging, reconfigure
from rentivo.observability import configure_tracing
from rentivo.observability.middleware import TracingMiddleware
from rentivo.services.container import RequestServices

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_tracing()
    initialize_db()
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
    app.include_router(api)

    @app.middleware("http")
    async def request_services(request: Request, call_next):
        request.state.db_conn = None
        request.state.services = _LazyServices(request)
        try:
            return await call_next(request)
        finally:
            if request.state.db_conn is not None:
                request.state.db_conn.close()

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        structlog.contextvars.clear_contextvars()
        request_id = request.headers.get("X-Request-ID") or str(ULID())
        structlog.contextvars.bind_contextvars(request_id=request_id, method=request.method, path=request.url.path)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()

    app.add_middleware(TracingMiddleware)

    @app.exception_handler(ProblemException)
    async def problem_exception_handler(request: Request, exc: ProblemException):
        return problem_response(exc.problem)

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
