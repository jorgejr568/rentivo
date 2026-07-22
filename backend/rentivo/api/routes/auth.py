from __future__ import annotations

import json
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from rentivo.api.authentication import (
    allow_mfa_setup,
    reject_out_of_band_credentials,
)
from rentivo.api.csrf import issue_csrf_token, require_csrf
from rentivo.api.dependencies import get_services, require_login_scope
from rentivo.api.errors import ProblemException, problem
from rentivo.api.principal import Principal
from rentivo.api.schemas.auth import (
    AcceptedResponse,
    AnalyticsEvent,
    AuthConfigResponse,
    AuthenticatedResponse,
    BootstrapAnalytics,
    BootstrapResponse,
    CredentialTransport,
    CSRFResponse,
    FeatureFlags,
    LoginRequest,
    MFARequiredResponse,
    MobileAuthorizationExchangeRequest,
    MobileAuthorizationRequest,
    MobileAuthorizationResponse,
    PasswordForgotRequest,
    PasswordResetRequest,
    SessionResponse,
    SignupRequest,
)
from rentivo.constants.api_scopes import APIScope
from rentivo.context import ANON_ACTOR, Actor
from rentivo.models.audit_log import AuditEventType
from rentivo.services.container import RequestServices
from rentivo.services.user_service import UserAlreadyRegisteredError
from rentivo.settings import settings

logger = structlog.get_logger(__name__)
_ANALYTICS_EVENT_HEADER = "X-Rentivo-Analytics-Event"
_ANALYTICS_REASON_HEADER = "X-Rentivo-Analytics-Reason"
router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(reject_out_of_band_credentials)],
)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _login_rate_identity(*, email: str, client_ip: str) -> str:
    return json.dumps((email, client_ip), separators=(",", ":"))


async def _verify_turnstile(request: Request, services: RequestServices, token: str) -> None:
    if not await services.turnstile.verify(token, _client_ip(request)):
        raise ProblemException.bad_request(
            "turnstile_failed",
            "Verificação de segurança falhou. Tente novamente.",
        )


def _set_access_cookie(response: Response, credential: str) -> None:
    response.set_cookie(
        settings.access_cookie_name,
        credential,
        max_age=settings.api_key_login_ttl_seconds,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _set_challenge_cookie(response: Response, nonce: str) -> None:
    response.set_cookie(
        settings.challenge_cookie_name,
        nonce,
        max_age=settings.auth_challenge_ttl_seconds,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _delete_cookie(response: Response, name: str, *, httponly: bool) -> None:
    response.delete_cookie(
        name,
        path="/",
        secure=settings.cookie_secure,
        httponly=httponly,
        samesite="lax",
    )


def _clear_auth_cookies(response: Response, *, include_challenge: bool) -> None:
    _delete_cookie(response, settings.access_cookie_name, httponly=True)
    _delete_cookie(response, settings.csrf_cookie_name, httponly=False)
    if include_challenge:
        _delete_cookie(response, settings.challenge_cookie_name, httponly=True)


def _copy_set_cookies(source: Response, target: Response) -> None:
    for value in source.headers.getlist("set-cookie"):
        target.headers.append("set-cookie", value)


def _authenticated_response(
    result: object,
    *,
    credential_transport: CredentialTransport = "cookie",
    include_credential: bool = True,
) -> JSONResponse:
    user = getattr(result, "user", None)
    api_key = getattr(result, "api_key", None)
    bootstrap = getattr(result, "bootstrap", None)
    credential = getattr(result, "access_credential", None)
    if user is None or api_key is None or bootstrap is None:
        raise RuntimeError("Authenticated login result is incomplete")
    principal = Principal(
        user=user,
        api_key=api_key,
        source="web" if credential_transport == "cookie" else "mobile",
    )
    csrf_cookie = Response()
    csrf_token = issue_csrf_token(csrf_cookie, principal)
    bootstrap_response = BootstrapResponse.model_validate({**bootstrap, "csrf_token": csrf_token})
    analytics_event = getattr(result, "analytics_event", None)
    if analytics_event is not None:
        bootstrap_response = bootstrap_response.model_copy(
            update={
                "analytics": BootstrapAnalytics(
                    gtm_container_id=bootstrap_response.analytics.gtm_container_id,
                    events=(*bootstrap_response.analytics.events, AnalyticsEvent.model_validate(analytics_event)),
                )
            }
        )
    if include_credential and credential is None:
        raise RuntimeError("Authenticated login result has no access credential")
    expose_credential = credential_transport == "body" and include_credential
    if include_credential:
        payload = AuthenticatedResponse.model_validate(
            {
                "credential_transport": credential_transport,
                "bootstrap": bootstrap_response,
                **(
                    {
                        "access_token": credential,
                        "token_type": "Bearer",
                        "expires_in": settings.api_key_login_ttl_seconds,
                    }
                    if expose_credential
                    else {}
                ),
            }
        )
    else:
        payload = SessionResponse(bootstrap=bootstrap_response)
    response = JSONResponse(payload.model_dump(mode="json"))
    if credential_transport == "cookie":
        _copy_set_cookies(csrf_cookie, response)
    if credential_transport == "cookie" and include_credential:
        _set_access_cookie(response, credential)
    response.headers["Cache-Control"] = "no-store"
    return response


def _mfa_response(
    result: object,
    *,
    credential_transport: CredentialTransport = "cookie",
) -> JSONResponse:
    challenge_id = getattr(result, "challenge_id", None)
    challenge_nonce = getattr(result, "challenge_nonce", None)
    methods = tuple(getattr(result, "methods", ()))
    if challenge_id is None or challenge_nonce is None:
        raise RuntimeError("MFA login result is incomplete")
    payload = MFARequiredResponse.model_validate(
        {
            "credential_transport": credential_transport,
            "challenge_id": challenge_id,
            "methods": methods,
            **({"challenge_token": challenge_nonce} if credential_transport == "body" else {}),
        }
    )
    response = JSONResponse(payload.model_dump(mode="json"), status_code=202)
    if credential_transport == "cookie":
        _set_challenge_cookie(response, challenge_nonce)
    response.headers["Cache-Control"] = "no-store"
    return response


def _audit_login_failure(
    services: RequestServices,
    *,
    email: str,
    client_ip: str,
    source: str,
) -> None:
    services.audit.safe_log_for(
        Actor(user_id=None, email="", source=source),
        AuditEventType.USER_LOGIN_FAILED,
        entity_type="user",
        new_state={"email": email},
        metadata={"ip": client_ip},
    )


def _login_failure_problem(*, rate_limited: bool) -> ProblemException:
    if rate_limited:
        value = problem(
            status=429,
            code="login_rate_limited",
            title="Muitas tentativas",
            detail="Muitas tentativas. Aguarde um momento antes de tentar novamente.",
        )
        reason = "rate_limited"
    else:
        value = problem(
            status=401,
            code="invalid_credentials",
            title="Não autenticado",
            detail="E-mail ou senha inválidos.",
        )
        reason = "bad_credentials"
    return ProblemException(
        value,
        headers={
            _ANALYTICS_EVENT_HEADER: "rentivo_login_failed",
            _ANALYTICS_REASON_HEADER: reason,
        },
    )


@router.post("/signup", response_model=AuthenticatedResponse)
async def signup(
    payload: SignupRequest,
    request: Request,
    services: RequestServices = Depends(get_services),
) -> JSONResponse:
    await _verify_turnstile(request, services, payload.turnstile_token)
    try:
        result = services.login.signup(
            email=payload.email,
            password=payload.password,
            client_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
            source="web" if payload.credential_transport == "cookie" else "mobile",
        )
    except UserAlreadyRegisteredError:
        raise ProblemException.bad_request("email_already_registered", "E-mail já cadastrado.") from None
    return _authenticated_response(result, credential_transport=payload.credential_transport)


@router.post(
    "/login",
    response_model=AuthenticatedResponse,
    responses={202: {"model": MFARequiredResponse}},
)
async def login(
    payload: LoginRequest,
    request: Request,
    services: RequestServices = Depends(get_services),
) -> JSONResponse:
    client_ip = _client_ip(request)
    rate_identity = _login_rate_identity(email=payload.email, client_ip=client_ip)
    await _verify_turnstile(request, services, payload.turnstile_token)
    if not services.auth_rate_limit.reserve(
        action="login",
        identity=rate_identity,
        limit=5,
        window_seconds=60,
    ):
        raise _login_failure_problem(rate_limited=True)
    try:
        source = "web" if payload.credential_transport == "cookie" else "mobile"
        result = services.login.login(
            email=payload.email,
            password=payload.password,
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent", ""),
            source=source,
        )
    except ProblemException as exc:
        if exc.problem.code == "invalid_credentials":
            _audit_login_failure(
                services,
                email=payload.email,
                client_ip=client_ip,
                source=source,
            )
            raise _login_failure_problem(rate_limited=False) from None
        raise
    if result is None:
        _audit_login_failure(
            services,
            email=payload.email,
            client_ip=client_ip,
            source=source,
        )
        raise _login_failure_problem(rate_limited=False)
    services.auth_rate_limit.clear(action="login", identity=rate_identity)
    if result.status == "mfa_required":
        return _mfa_response(result, credential_transport=payload.credential_transport)
    return _authenticated_response(result, credential_transport=payload.credential_transport)


_login_principal = require_login_scope(APIScope.PROFILE_READ)


def _invalid_mobile_authorization() -> ProblemException:
    return ProblemException.unauthorized(
        "invalid_or_expired_mobile_authorization",
        "Autorização móvel inválida ou expirada.",
    )


@router.post("/mobile/authorize", response_model=MobileAuthorizationResponse, status_code=201)
async def authorize_mobile(
    payload: MobileAuthorizationRequest,
    principal: Principal = Depends(_login_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> MobileAuthorizationResponse:
    issued = services.auth_challenge.issue(
        user_id=principal.user.id,
        phase="mobile_authorization",
        allowed_methods=("exchange",),
    )
    return MobileAuthorizationResponse(
        authorization_code=f"{issued.challenge.uuid}.{issued.nonce}", state=payload.state
    )


@router.post("/mobile/exchange", response_model=AuthenticatedResponse)
async def exchange_mobile_authorization(
    payload: MobileAuthorizationExchangeRequest,
    request: Request,
    services: RequestServices = Depends(get_services),
) -> JSONResponse:
    challenge_id, separator, nonce = payload.authorization_code.partition(".")
    if not separator or not challenge_id or not nonce:
        raise _invalid_mobile_authorization()
    challenge = services.auth_challenge.consume(
        challenge_id,
        nonce,
        expected_phase="mobile_authorization",
        expected_method="exchange",
    )
    if challenge is None or challenge.user_id is None:
        raise _invalid_mobile_authorization()
    user = services.user.get_by_id(challenge.user_id)
    if user is None:
        raise _invalid_mobile_authorization()
    result = services.login.complete_login(
        user=user,
        via="mobile_authorization",
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        source="mobile",
    )
    return _authenticated_response(result, credential_transport="body")


@router.get("/session", response_model=SessionResponse)
async def session(
    _allow_mfa_setup: None = Depends(allow_mfa_setup),
    principal: Principal = Depends(_login_principal),
    services: RequestServices = Depends(get_services),
) -> JSONResponse:
    result = type(
        "SessionResult",
        (),
        {
            "user": principal.user,
            "api_key": principal.api_key,
            "bootstrap": services.login.bootstrap(principal),
        },
    )()
    return _authenticated_response(
        result,
        credential_transport="body" if principal.source == "mobile" else "cookie",
        include_credential=False,
    )


@router.post("/logout", status_code=204)
async def logout(
    _allow_mfa_setup: None = Depends(allow_mfa_setup),
    principal: Principal = Depends(_login_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    services.api_key.logout(principal.api_key)
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.USER_LOGOUT,
        entity_type="user",
        entity_id=principal.user.id,
    )
    response = Response(status_code=204)
    response.headers[_ANALYTICS_EVENT_HEADER] = "rentivo_logout"
    _clear_auth_cookies(response, include_challenge=False)
    return response


@router.post("/password/forgot", response_model=AcceptedResponse, status_code=202)
async def password_forgot(
    payload: PasswordForgotRequest,
    request: Request,
    services: RequestServices = Depends(get_services),
) -> JSONResponse:
    client_ip = _client_ip(request)
    await _verify_turnstile(request, services, payload.turnstile_token)
    if not services.auth_rate_limit.reserve(
        action="password_reset",
        identity=client_ip,
        limit=5,
        window_seconds=60,
    ):
        raise ProblemException(
            problem(
                status=429,
                code="password_reset_rate_limited",
                title="Muitas tentativas",
                detail="Muitas tentativas. Aguarde um momento antes de tentar novamente.",
            )
        )
    try:
        services.password_reset.request_reset(payload.email)
    except Exception:
        logger.warning("password_reset_dispatch_failed")
    services.audit.safe_log_for(
        getattr(request.state, "actor", ANON_ACTOR),
        AuditEventType.USER_PASSWORD_RESET_REQUESTED,
        entity_type="user",
        new_state={"email": payload.email},
    )
    response = AcceptedResponse(analytics_events=(AnalyticsEvent(event="rentivo_password_reset_requested"),))
    return JSONResponse(
        response.model_dump(mode="json"),
        status_code=202,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/password/reset", status_code=204)
async def password_reset(
    payload: PasswordResetRequest,
    request: Request,
    services: RequestServices = Depends(get_services),
) -> Response:
    user_id = services.password_reset.consume(payload.token, payload.password)
    if user_id is None:
        raise ProblemException.bad_request(
            "invalid_or_expired_reset_token",
            "Token de redefinição inválido ou expirado.",
        )
    user = services.user.get_by_id(user_id)
    actor = Actor(
        user_id=user_id,
        email="" if user is None else user.email,
        source="web",
    )
    if user is not None:
        try:
            services.job.enqueue_for(
                actor,
                "email.send",
                {
                    "event": "password_reset_completed",
                    "to_email": user.email,
                    "ctx": {
                        "email": user.email,
                        "changed_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "source_ip": _client_ip(request),
                    },
                },
            )
        except Exception:
            logger.warning("password_reset_confirmation_dispatch_failed", user_id=user_id)
    services.audit.safe_log_for(
        actor,
        AuditEventType.USER_PASSWORD_RESET_COMPLETED,
        entity_type="user",
        entity_id=user_id,
    )
    response = Response(status_code=204)
    response.headers["X-Rentivo-Analytics-Event"] = "rentivo_password_reset_completed"
    _clear_auth_cookies(response, include_challenge=True)
    return response


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config(services: RequestServices = Depends(get_services)) -> AuthConfigResponse:
    turnstile_enabled = services.turnstile.is_enabled
    return AuthConfigResponse(
        feature_flags=FeatureFlags(
            google_auth=services.google_auth.is_enabled,
            turnstile=turnstile_enabled,
            turnstile_site_key=services.turnstile.site_key if turnstile_enabled else "",
        ),
        analytics={"gtm_container_id": settings.gtm_container_id},
    )


@router.get("/csrf", response_model=CSRFResponse)
async def csrf_token(principal: Principal = Depends(_login_principal)) -> JSONResponse:
    cookie_response = Response()
    token = issue_csrf_token(cookie_response, principal)
    response = JSONResponse({"csrf_token": token}, headers={"Cache-Control": "no-store"})
    _copy_set_cookies(cookie_response, response)
    return response
