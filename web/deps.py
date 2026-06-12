from __future__ import annotations

from functools import cache

import structlog
from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from rentivo.db import get_engine
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,  # noqa: F401 — re-exported for test patches
    SQLAlchemyInviteRepository,
    SQLAlchemyUserRepository,
)
from rentivo.settings import settings
from rentivo.storage.factory import get_storage  # noqa: F401 — re-exported for test patches
from web.analytics import attach_to_context
from web.flash import get_flashed_messages

logger = structlog.get_logger(__name__)

PUBLIC_PREFIX_PATHS = {
    "/login",
    "/signup",
    "/static",
    "/mfa-verify",
    "/security/passkeys/auth",
    "/forgot-password",
    "/reset-password",
    "/auth/google",
}
PUBLIC_EXACT_PATHS = {"/", "/robots.txt", "/sitemap.xml", "/health"}

# Paths that MFA-enforcement redirect allows even when mfa_setup_required is set
MFA_EXEMPT_PREFIXES = {"/security", "/logout", "/login", "/signup", "/static", "/mfa-verify"}
MFA_EXEMPT_EXACT = {"/", "/robots.txt", "/sitemap.xml", "/health"}


@cache
def _get_route_prefixes(app: ASGIApp) -> frozenset[str]:
    """Extract first path segments from registered routes (cached at startup)."""
    return frozenset(
        segment
        for route in getattr(app, "routes", ())
        if (segment := getattr(route, "path", "").strip("/").split("/")[0])
    )


def _path_matches_route(scope: Scope) -> bool:
    """O(1) check whether the request path could match a registered route."""
    app = scope.get("app")
    if not app:
        return True
    first_segment = scope.get("path", "").strip("/").split("/")[0]
    return first_segment in _get_route_prefixes(app)


class AuthMiddleware:
    """Pure ASGI middleware for authentication checks."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Local import — web.deps is imported during app boot; avoid cycles.
        from web.context import actor_from_session

        request = Request(scope, receive)
        # Attach the per-request actor up front so every downstream
        # handler / service can rely on `request.state.actor` existing
        # regardless of authentication state (ANON_ACTOR for anonymous).
        request.state.actor = actor_from_session(request.session)

        path = request.url.path
        if path in PUBLIC_EXACT_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIX_PATHS):
            await self.app(scope, receive, send)
            return
        user_id = request.session.get("user_id")
        if not user_id:
            if not _path_matches_route(scope):
                await self.app(scope, receive, send)
                return

            logger.info("auth_redirect", reason="no_session")
            response = RedirectResponse("/login", status_code=302)
            await response(scope, receive, send)
            return
        # Bind identity for all downstream logs in this request.
        structlog.contextvars.bind_contextvars(
            user_id=user_id,
            email=request.session.get("email"),
        )
        await self.app(scope, receive, send)


class MFAEnforcementMiddleware:
    """Pure ASGI middleware — forces users in MFA-enforcing orgs to set up MFA."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        # Skip for public/exempt paths
        if path in MFA_EXEMPT_EXACT or any(path.startswith(p) for p in MFA_EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        user_id = request.session.get("user_id")
        if not user_id:
            await self.app(scope, receive, send)
            return

        if request.session.get("mfa_setup_required"):
            logger.info("mfa_enforcement_redirect")
            response = RedirectResponse("/security/totp/setup", status_code=302)
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
                logger.debug("db_connection_closed")


def _get_conn(request: Request):
    """Lazy per-request connection — created on first use, closed by middleware."""
    if request.state.db_conn is None:
        logger.debug("db_connection_opened")
        request.state.db_conn = get_engine().connect()
    return request.state.db_conn


class RequestServicesMiddleware:
    """Pure ASGI — attaches a lazy services proxy to request.state.services.

    Must run AFTER DBConnectionMiddleware (i.e. registered immediately after it
    in web/app.py) so the proxy can rely on request.state.db_conn existing.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        request.state.services = _LazyServicesProxy(request)
        await self.app(scope, receive, send)


class _LazyServicesProxy:
    """Defers RequestServices construction until first attribute access.

    Keeps the per-request overhead at zero for endpoints that do not touch
    any service (e.g. /health, /static).
    """

    __slots__ = ("_request", "_real")

    def __init__(self, request) -> None:
        self._request = request
        self._real = None

    def _get(self):
        if self._real is None:
            from rentivo.encryption.factory import get_encryption
            from web.services_container import RequestServices

            self._real = RequestServices(
                conn=_get_conn(self._request),
                encryption=get_encryption(),
            )
        return self._real

    def __getattr__(self, name):
        return getattr(self._get(), name)


def _hydrate_legacy_session_email(request: Request, user_id: int | None) -> str | None:
    """Pre-migration sessions had `username` but no `email`. Backfill once from the DB so
    existing browsers keep rendering the navbar without forcing a logout."""
    email = request.session.get("email")
    if not user_id or email:
        return email
    from rentivo.encryption.factory import get_encryption

    user = SQLAlchemyUserRepository(_get_conn(request), get_encryption()).get_by_id(user_id)
    if user is not None:
        email = user.email
        request.session["email"] = email
    request.session.pop("username", None)
    return email


def render(request: Request, template_name: str, context: dict | None = None) -> Response:
    from web.app import templates
    from web.csrf import get_csrf_token

    logger.debug("template_render", template=template_name)
    ctx = context or {}
    ctx["request"] = request
    user_id = request.session.get("user_id")
    email = _hydrate_legacy_session_email(request, user_id)
    ctx["user"] = email
    ctx["user_id"] = user_id
    ctx["messages"] = get_flashed_messages(request)
    ctx["csrf_token"] = get_csrf_token(request)

    if user_id and "pending_invite_count" not in ctx:
        try:
            from rentivo.encryption.factory import get_encryption

            conn = _get_conn(request)
            invite_repo = SQLAlchemyInviteRepository(conn, get_encryption())
            ctx["pending_invite_count"] = invite_repo.count_pending_for_user(user_id)
        except Exception:
            ctx["pending_invite_count"] = 0
    else:
        ctx.setdefault("pending_invite_count", 0)

    attach_to_context(request, template_name, ctx)
    ctx["turnstile_site_key"] = settings.turnstile_site_key
    ctx["google_auth_enabled"] = settings.google_auth_enabled

    return templates.TemplateResponse(request, template_name, ctx)
