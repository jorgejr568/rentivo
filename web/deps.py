from __future__ import annotations

from functools import cache

import structlog
from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from rentivo.db import get_engine
from rentivo.jobs.sqlalchemy import SQLAlchemyJobRepository
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyAuditLogRepository,
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyInviteRepository,
    SQLAlchemyKnownDeviceRepository,
    SQLAlchemyMFATOTPRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyPasskeyRepository,
    SQLAlchemyPasswordResetTokenRepository,
    SQLAlchemyReceiptRepository,
    SQLAlchemyRecoveryCodeRepository,
    SQLAlchemyThemeRepository,
    SQLAlchemyUserRepository,
)
from rentivo.services.audit_service import AuditService
from rentivo.services.authorization_service import AuthorizationService
from rentivo.services.bill_service import BillService
from rentivo.services.billing_service import BillingService
from rentivo.services.invite_service import InviteService
from rentivo.services.job_service import JobService
from rentivo.services.known_device_service import KnownDeviceService
from rentivo.services.mfa_service import MFAService
from rentivo.services.organization_service import OrganizationService
from rentivo.services.password_reset_service import PasswordResetService
from rentivo.services.pix_service import PixService
from rentivo.services.storage_cleanup_service import StorageCleanupService
from rentivo.services.theme_service import ThemeService
from rentivo.services.turnstile_service import TurnstileService
from rentivo.services.user_service import UserService
from rentivo.settings import settings
from rentivo.storage.factory import get_storage
from web.analytics import build_page_context, pop_events
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

        request = Request(scope, receive)
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


def get_billing_service(request: Request) -> BillingService:
    from rentivo.encryption.factory import get_encryption

    return BillingService(SQLAlchemyBillingRepository(_get_conn(request), get_encryption()))


def get_bill_service(request: Request) -> BillService:
    from rentivo.encryption.factory import get_encryption

    conn = _get_conn(request)
    return BillService(
        SQLAlchemyBillRepository(conn, get_encryption()),
        get_storage(),
        SQLAlchemyReceiptRepository(conn, get_encryption()),
        theme_service=get_theme_service(request),
        pix_service=get_pix_service(request),
        job_service=get_job_service(request),
        actor_source="web",
        actor_id=request.session.get("user_id"),
        actor_username=request.session.get("email", ""),
    )


def get_theme_service(request: Request) -> ThemeService:
    return ThemeService(SQLAlchemyThemeRepository(_get_conn(request)))


def get_pix_service(request: Request) -> PixService:
    from rentivo.encryption.factory import get_encryption

    conn = _get_conn(request)
    return PixService(
        SQLAlchemyUserRepository(conn, get_encryption()),
        SQLAlchemyOrganizationRepository(conn, get_encryption()),
    )


def get_user_service(request: Request) -> UserService:
    from rentivo.encryption.factory import get_encryption

    return UserService(SQLAlchemyUserRepository(_get_conn(request), get_encryption()))


def get_organization_service(request: Request) -> OrganizationService:
    from rentivo.encryption.factory import get_encryption

    return OrganizationService(SQLAlchemyOrganizationRepository(_get_conn(request), get_encryption()))


def get_invite_service(request: Request) -> InviteService:
    from rentivo.encryption.factory import get_encryption

    conn = _get_conn(request)
    return InviteService(
        SQLAlchemyInviteRepository(conn),
        SQLAlchemyOrganizationRepository(conn, get_encryption()),
        SQLAlchemyUserRepository(conn, get_encryption()),
    )


def get_authorization_service(request: Request) -> AuthorizationService:
    from rentivo.encryption.factory import get_encryption

    return AuthorizationService(SQLAlchemyOrganizationRepository(_get_conn(request), get_encryption()))


def get_audit_service(request: Request) -> AuditService:
    return AuditService(SQLAlchemyAuditLogRepository(_get_conn(request)))


def get_mfa_service(request: Request) -> MFAService:
    from rentivo.encryption.factory import get_encryption

    conn = _get_conn(request)
    return MFAService(
        SQLAlchemyMFATOTPRepository(conn, get_encryption()),
        SQLAlchemyRecoveryCodeRepository(conn),
        SQLAlchemyPasskeyRepository(conn),
        SQLAlchemyOrganizationRepository(conn, get_encryption()),
    )


def get_job_service(request: Request) -> JobService:
    conn = _get_conn(request)
    return JobService(
        SQLAlchemyJobRepository(conn, stuck_after_seconds=settings.job_worker_stuck_after_seconds),
        AuditService(SQLAlchemyAuditLogRepository(conn)),
    )


def get_storage_cleanup_service(request: Request) -> StorageCleanupService:
    from rentivo.encryption.factory import get_encryption

    conn = _get_conn(request)
    return StorageCleanupService(
        job_service=get_job_service(request),
        bill_repo=SQLAlchemyBillRepository(conn, get_encryption()),
        receipt_repo=SQLAlchemyReceiptRepository(conn, get_encryption()),
    )


def get_known_device_service(request: Request) -> KnownDeviceService:
    return KnownDeviceService(SQLAlchemyKnownDeviceRepository(_get_conn(request)))


def get_turnstile_service(request: Request) -> TurnstileService:
    return TurnstileService(
        site_key=settings.turnstile_site_key,
        secret_key=settings.turnstile_secret_key,
        verify_url=settings.turnstile_verify_url,
    )


def get_password_reset_service(request: Request) -> PasswordResetService:
    from rentivo.encryption.factory import get_encryption

    conn = _get_conn(request)
    user_repo = SQLAlchemyUserRepository(conn, get_encryption())
    return PasswordResetService(
        user_repo=user_repo,
        token_repo=SQLAlchemyPasswordResetTokenRepository(conn),
        job_service=get_job_service(request),
        user_service=UserService(user_repo),
        public_app_url=settings.public_app_url,
    )


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
            conn = _get_conn(request)
            invite_repo = SQLAlchemyInviteRepository(conn)
            ctx["pending_invite_count"] = invite_repo.count_pending_for_user(user_id)
        except Exception:
            ctx["pending_invite_count"] = 0
    else:
        ctx.setdefault("pending_invite_count", 0)

    ctx["gtm_initial_push"] = build_page_context(request, template_name, ctx)
    ctx["gtm_pending_events"] = pop_events(request)
    ctx["turnstile_site_key"] = settings.turnstile_site_key

    return templates.TemplateResponse(request, template_name, ctx)
