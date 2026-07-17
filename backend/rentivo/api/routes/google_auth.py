from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from rentivo.api.authentication import reject_out_of_band_credentials
from rentivo.api.dependencies import get_services
from rentivo.api.errors import Problem, ProblemException, problem, problem_response
from rentivo.api.routes.auth import (
    _ANALYTICS_EVENT_HEADER,
    _authenticated_response,
    _client_ip,
    _copy_set_cookies,
    _delete_cookie,
    _mfa_response,
    _set_challenge_cookie,
)
from rentivo.api.schemas.auth import AuthenticatedResponse, MFARequiredResponse
from rentivo.services.container import RequestServices
from rentivo.settings import settings

router = APIRouter(
    prefix="/auth/google",
    tags=["auth"],
    dependencies=[Depends(reject_out_of_band_credentials)],
)


def _accepts_json(request: Request) -> bool:
    return any(
        item.partition(";")[0].strip().lower() == "application/json"
        for item in request.headers.get("accept", "").split(",")
    )


def _failure_response(*, as_json: bool) -> JSONResponse | RedirectResponse:
    if as_json:
        response = problem_response(
            problem(
                status=401,
                code="google_auth_failed",
                title="Não autenticado",
                detail="Não foi possível entrar com o Google. Tente novamente.",
            )
        )
    else:
        response = RedirectResponse("/login?error=google_auth_failed", status_code=302)
    _delete_cookie(response, settings.challenge_cookie_name, httponly=True)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get(
    "/start",
    status_code=302,
    response_class=RedirectResponse,
    responses={404: {"model": Problem}},
)
async def google_start(services: RequestServices = Depends(get_services)) -> RedirectResponse:
    if not services.google_auth.is_enabled:
        raise ProblemException.not_found()
    issued = services.auth_challenge.issue(
        user_id=None,
        phase="oauth",
        allowed_methods=("google",),
    )
    response = RedirectResponse(
        services.google_auth.build_authorization_url(issued.challenge.uuid),
        status_code=302,
    )
    _set_challenge_cookie(response, issued.nonce)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get(
    "/callback",
    response_model=AuthenticatedResponse,
    responses={
        202: {"model": MFARequiredResponse},
        302: {"description": "Redirecionamento para navegação direta"},
        401: {"model": Problem},
        404: {"model": Problem},
    },
)
async def google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    services: RequestServices = Depends(get_services),
) -> JSONResponse | RedirectResponse:
    if not services.google_auth.is_enabled:
        raise ProblemException.not_found()
    as_json = _accepts_json(request)
    nonce = request.cookies.get(settings.challenge_cookie_name, "")
    consumed = None
    if state and nonce:
        consumed = services.auth_challenge.consume(
            state,
            nonce,
            expected_phase="oauth",
            expected_method="google",
        )
    if consumed is None or error or not code:
        return _failure_response(as_json=as_json)
    info = await services.google_auth.exchange_code(code)
    if info is None or not info.email_verified:
        return _failure_response(as_json=as_json)
    result = services.login.login_with_google(
        email=info.email,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    if result.status == "mfa_required":
        if result.challenge_id is None or result.challenge_nonce is None:
            raise RuntimeError("Google MFA result is incomplete")
        if as_json:
            response = _mfa_response(result)
        else:
            response = RedirectResponse(
                f"/mfa-verify?challenge={result.challenge_id}",
                status_code=302,
            )
            _set_challenge_cookie(response, result.challenge_nonce)
    else:
        cookie_response = _authenticated_response(result, set_access_cookie=True)
        if as_json:
            response = cookie_response
            _delete_cookie(response, settings.challenge_cookie_name, httponly=True)
        else:
            response = RedirectResponse("/billings/", status_code=302)
            _copy_set_cookies(cookie_response, response)
            _delete_cookie(response, settings.challenge_cookie_name, httponly=True)
            analytics_event = result.analytics_event or {}
            if event_name := analytics_event.get("event"):
                response.headers[_ANALYTICS_EVENT_HEADER] = str(event_name)
    response.headers["Cache-Control"] = "no-store"
    return response
