"""CSRF protection using synchronizer token pattern.

Each form gets a hidden csrf_token field. The token is stored in the session
and verified on POST/PUT/DELETE/PATCH requests.

Uses a pure ASGI middleware (not BaseHTTPMiddleware) to avoid consuming the
request body — downstream handlers can still read request.form().
"""

from __future__ import annotations

import secrets
from typing import Any

import structlog
from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from web.flash import flash

logger = structlog.get_logger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
# Only JSON webauthn endpoints need the blanket exemption. The passkey delete
# route (/security/passkeys/{uuid}/delete) is a form POST and must go through
# CSRF — exempting the whole /security/passkeys prefix would let an attacker
# cross-origin-submit a form and remove the victim's MFA factor.
EXEMPT_PATHS = {
    "/login",
    "/signup",
    "/static",
    "/security/passkeys/register",
    "/security/passkeys/auth",
    "/mfa-verify",
    # PSP payment webhook: JSON POST authenticated by shared-secret header, with
    # no session/CSRF token (the caller is Asaas, not a browser form).
    "/webhooks",
}


def get_csrf_token(request: Request) -> str:
    """Get or create a CSRF token for the current session."""
    token = request.session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["_csrf_token"] = token
        logger.debug("csrf_token_generated")
    return token


def _verify_csrf_token(request: Request, form_token: str) -> bool:
    """Verify the submitted CSRF token matches the session token."""
    session_token = request.session.get("_csrf_token", "")
    if not session_token or not form_token:
        return False
    return secrets.compare_digest(session_token, form_token)


def _reject(request: Request) -> RedirectResponse:
    """Flash an expired-session message and redirect back to the referer."""
    flash(request, "Sessão expirada. Tente novamente.", "danger")
    referer = request.headers.get("referer", "/")
    return RedirectResponse(referer, status_code=302)


class CSRFMiddleware:
    """Pure ASGI middleware for CSRF verification.

    Reads the request body to extract the csrf_token, then replays the body
    so downstream handlers can read it again via request.form().
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        if request.method in SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        path = request.url.path
        if any(path.startswith(p) for p in EXEMPT_PATHS):
            await self.app(scope, receive, send)
            return

        # 1. Header-token fast path — works for JSON and any non-form request.
        header_token = request.headers.get("X-CSRF-Token", "")
        if header_token:
            if not _verify_csrf_token(request, header_token):
                logger.warning("csrf_token_mismatch", source="header")
                await _reject(request)(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        # 2. Form-body path — read body, extract csrf_token field, replay body.
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" not in content_type and "application/x-www-form-urlencoded" not in content_type:
            # No header token AND no form body — nothing to verify. Reject.
            logger.warning("csrf_token_missing", content_type=content_type)
            await _reject(request)(scope, receive, send)
            return

        body = await request.body()
        form = await request.form()
        form_token = str(form.get("csrf_token", ""))
        await form.close()

        if not _verify_csrf_token(request, form_token):
            logger.warning("csrf_token_mismatch", source="form")
            await _reject(request)(scope, receive, send)
            return

        # Replay body so downstream handlers can read request.form()
        async def replay_receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay_receive, send)
