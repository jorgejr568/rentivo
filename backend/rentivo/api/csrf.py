from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from fastapi import Depends, Request
from starlette.responses import Response

from rentivo.api.authentication import get_principal
from rentivo.api.errors import ProblemException
from rentivo.api.principal import Principal
from rentivo.settings import settings

CSRF_COOKIE_NAME = settings.csrf_cookie_name
CSRF_HEADER_NAME = "X-CSRF-Token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


def _signature(api_key_uuid: str, nonce: str) -> str:
    digest = hmac.new(
        settings.get_secret_key().encode(),
        f"{api_key_uuid}:{nonce}".encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _valid_token(token: str, api_key_uuid: str) -> bool:
    try:
        nonce, signature = token.split(".", 1)
    except ValueError:
        return False
    if not nonce or not signature:
        return False
    return _constant_time_equal(signature, _signature(api_key_uuid, nonce))


def issue_csrf_token(response: Response, principal: Principal) -> str:
    nonce = secrets.token_urlsafe(32)
    token = f"{nonce}.{_signature(principal.api_key.uuid, nonce)}"
    response.set_cookie(
        settings.csrf_cookie_name,
        token,
        secure=settings.cookie_secure,
        httponly=False,
        samesite="lax",
        path="/",
    )
    return token


async def require_csrf(
    request: Request,
    principal: Principal = Depends(get_principal),
) -> None:
    if request.method in _SAFE_METHODS or request.state.auth_transport == "bearer":
        return
    cookie_token = request.cookies.get(settings.csrf_cookie_name, "")
    header_token = request.headers.get(CSRF_HEADER_NAME, "")
    if (
        not cookie_token
        or not header_token
        or not _constant_time_equal(cookie_token, header_token)
        or not _valid_token(cookie_token, principal.api_key.uuid)
    ):
        raise ProblemException.forbidden("csrf_failed", "Token CSRF inválido ou expirado.")
