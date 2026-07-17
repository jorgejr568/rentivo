from __future__ import annotations

import json
import secrets
from typing import Any

import structlog
from fastapi import Depends, Request

from rentivo.api.dependencies import get_services
from rentivo.api.errors import ProblemException
from rentivo.api.principal import Principal
from rentivo.context import ANON_ACTOR
from rentivo.services.container import RequestServices
from rentivo.settings import settings

ACCESS_COOKIE_NAME = settings.access_cookie_name
_OUT_OF_BAND_CREDENTIAL_FIELDS = frozenset({"api_key", "access_token"})


def _constant_time_equal(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode(), right.encode())


def _contains_out_of_band_credential(value: Any) -> bool:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            if any(str(key).lower() in _OUT_OF_BAND_CREDENTIAL_FIELDS for key in current):
                return True
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return False


async def reject_out_of_band_credentials(request: Request) -> None:
    if any(key.lower() in _OUT_OF_BAND_CREDENTIAL_FIELDS for key in request.query_params):
        raise ProblemException.bad_request(
            "malformed_credentials",
            "A chave deve ser enviada apenas por cookie ou cabeçalho Authorization Bearer.",
        )
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type in {"application/x-www-form-urlencoded", "multipart/form-data"}:
        await request.body()
        form = await request.form()
        if any(str(key).lower() in _OUT_OF_BAND_CREDENTIAL_FIELDS for key in form):
            raise ProblemException.bad_request(
                "malformed_credentials",
                "A chave deve ser enviada apenas por cookie ou cabeçalho Authorization Bearer.",
            )
    elif media_type == "application/json" or media_type.endswith("+json"):
        body = await request.body()
        if body:
            try:
                payload = json.loads(body)
            except TypeError, ValueError:
                payload = None
            if _contains_out_of_band_credential(payload):
                raise ProblemException.bad_request(
                    "malformed_credentials",
                    "A chave deve ser enviada apenas por cookie ou cabeçalho Authorization Bearer.",
                )
    _credential_transport(request)


def _bearer_credential(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if authorization is None:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise ProblemException.bad_request("malformed_credentials", "Cabeçalho de autenticação inválido.")
    return parts[1]


def _credential_transport(request: Request) -> tuple[str | None, str | None]:
    cookie_credential = request.cookies.get(settings.access_cookie_name)
    bearer_credential = _bearer_credential(request)
    if (
        cookie_credential is not None
        and bearer_credential is not None
        and not _constant_time_equal(cookie_credential, bearer_credential)
    ):
        raise ProblemException.bad_request(
            "ambiguous_credentials",
            "A requisição contém credenciais de identidades diferentes.",
        )
    return cookie_credential, bearer_credential


async def get_optional_principal(
    request: Request,
    services: RequestServices = Depends(get_services),
) -> Principal | None:
    await reject_out_of_band_credentials(request)
    cookie_credential, bearer_credential = _credential_transport(request)

    credential = cookie_credential or bearer_credential
    if credential is None:
        request.state.actor = ANON_ACTOR
        request.state.auth_transport = None
        return None

    key = services.api_key.authenticate(credential)
    if key is None:
        request.state.clear_auth_cookies = cookie_credential is not None
        raise ProblemException.unauthorized("invalid_credentials", "Credencial inválida ou expirada.")
    user = services.user.get_by_id(key.user_id)
    if user is None:
        request.state.clear_auth_cookies = cookie_credential is not None
        raise ProblemException.unauthorized("invalid_credentials", "Credencial inválida ou expirada.")

    if key.is_login_token:
        source = "web" if cookie_credential is not None else "mobile"
    else:
        source = "integration"
    principal = Principal(user=user, api_key=key, source=source)
    request.state.principal = principal
    request.state.actor = principal.actor
    request.state.auth_transport = "cookie" if cookie_credential is not None else "bearer"
    structlog.contextvars.bind_contextvars(
        user_id=user.id,
        email=user.email,
        actor_source=source,
        api_key_uuid=key.uuid,
        api_key_class="login" if key.is_login_token else "integration",
    )
    return principal


async def get_principal(principal: Principal | None = Depends(get_optional_principal)) -> Principal:
    if principal is None:
        raise ProblemException.unauthorized("authentication_required", "Autenticação necessária.")
    return principal
