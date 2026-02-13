"""CSRF protection using synchronizer token pattern.

Each form gets a hidden csrf_token field. The token is stored in the session
and verified on POST/PUT/DELETE/PATCH requests.

Uses a pure ASGI middleware (not BaseHTTPMiddleware) to avoid consuming the
request body — downstream handlers can still read request.form().
"""
from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from web.flash import flash

logger = logging.getLogger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
EXEMPT_PATHS = {"/login", "/signup", "/static"}


def get_csrf_token(request: Request) -> str:
    """Get or create a CSRF token for the current session."""
    token = request.session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["_csrf_token"] = token
    return token


def _verify_csrf_token(request: Request, form_token: str) -> bool:
    """Verify the submitted CSRF token matches the session token."""
    session_token = request.session.get("_csrf_token", "")
    if not session_token or not form_token:
        return False
    return secrets.compare_digest(session_token, form_token)


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

        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
            body = await request.body()
            form = await request.form()
            form_token = str(form.get("csrf_token", ""))
            await form.close()

            if not _verify_csrf_token(request, form_token):
                logger.warning("CSRF token mismatch for %s %s", request.method, path)
                flash(request, "Sessão expirada. Tente novamente.", "danger")
                referer = request.headers.get("referer", "/")
                response = RedirectResponse(referer, status_code=302)
                await response(scope, receive, send)
                return

            # Replay body so downstream handlers can read request.form()
            async def replay_receive() -> dict[str, Any]:
                return {"type": "http.request", "body": body, "more_body": False}

            await self.app(scope, replay_receive, send)
            return

        await self.app(scope, receive, send)
