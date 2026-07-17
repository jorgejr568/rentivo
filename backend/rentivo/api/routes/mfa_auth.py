from __future__ import annotations

import json
from typing import Any, Literal

import structlog
import webauthn
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

from rentivo.api.authentication import reject_out_of_band_credentials
from rentivo.api.dependencies import get_services
from rentivo.api.errors import ProblemException, problem
from rentivo.api.routes.auth import _authenticated_response, _client_ip, _delete_cookie
from rentivo.api.schemas.auth import (
    AuthenticatedResponse,
    MFACodeVerifyRequest,
    PasskeyAuthBeginRequest,
    PasskeyAuthCompleteRequest,
)
from rentivo.context import Actor
from rentivo.models.audit_log import AuditEventType
from rentivo.models.auth_challenge import AuthChallenge
from rentivo.services.container import RequestServices
from rentivo.settings import settings

logger = structlog.get_logger(__name__)
router = APIRouter(
    prefix="/auth/mfa",
    tags=["auth"],
    dependencies=[Depends(reject_out_of_band_credentials)],
)

_MFA_LIMIT = 5
_MFA_WINDOW_SECONDS = 300


def _invalid_challenge() -> ProblemException:
    return ProblemException.unauthorized(
        "invalid_or_expired_challenge",
        "Desafio de autenticação inválido ou expirado.",
    )


def _invalid_code() -> ProblemException:
    return ProblemException.unauthorized("invalid_mfa_code", "Código de verificação inválido.")


def _invalid_passkey() -> ProblemException:
    return ProblemException.unauthorized("invalid_passkey", "Não foi possível verificar a passkey.")


def _rate_limited() -> ProblemException:
    return ProblemException(
        problem(
            status=429,
            code="mfa_rate_limited",
            title="Muitas tentativas",
            detail="Muitas tentativas. Aguarde um momento antes de tentar novamente.",
        )
    )


def _nonce(request: Request) -> str:
    value = request.cookies.get(settings.challenge_cookie_name, "")
    if not value:
        raise _invalid_challenge()
    return value


def _actor(challenge: AuthChallenge, email: str) -> Actor:
    return Actor(user_id=challenge.user_id, email=email, source="web")


def _rate_identity(request: Request, challenge_id: str) -> str:
    return f"{_client_ip(request)}:{challenge_id}"


def _reserve_attempt(
    services: RequestServices,
    request: Request,
    challenge_id: str,
) -> str:
    identity = _rate_identity(request, challenge_id)
    if not services.auth_rate_limit.reserve(
        action="mfa_verify",
        identity=identity,
        limit=_MFA_LIMIT,
        window_seconds=_MFA_WINDOW_SECONDS,
    ):
        raise _rate_limited()
    return identity


def _audit_failure(
    services: RequestServices,
    challenge: AuthChallenge,
    *,
    email: str,
    client_ip: str,
    method: str,
) -> None:
    services.audit.safe_log_for(
        _actor(challenge, email),
        AuditEventType.MFA_VERIFY_FAILED,
        entity_type="user",
        entity_id=challenge.user_id,
        metadata={"ip": client_ip, "method": method},
    )


def _finish_login(
    *,
    services: RequestServices,
    request: Request,
    user: object,
    via: str,
    audit_metadata: dict[str, Any],
    identity: str,
) -> JSONResponse:
    services.auth_rate_limit.clear(action="mfa_verify", identity=identity)
    result = services.login.complete_login(
        user=user,
        via=via,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        audit_metadata=audit_metadata,
    )
    response = _authenticated_response(result, set_access_cookie=True)
    _delete_cookie(response, settings.challenge_cookie_name, httponly=True)
    return response


async def _verify_code(
    method: Literal["totp", "recovery"],
    payload: MFACodeVerifyRequest,
    request: Request,
    services: RequestServices,
) -> JSONResponse:
    nonce = _nonce(request)
    challenge = services.auth_challenge.get_valid(
        payload.challenge_id,
        nonce,
        expected_phase="login",
        expected_method=method,
    )
    if challenge is None or challenge.user_id is None:
        raise _invalid_challenge()
    user = services.user.get_by_id(challenge.user_id)
    if user is None:
        raise _invalid_challenge()
    identity = _reserve_attempt(services, request, payload.challenge_id)
    verified = (
        services.mfa.verify_totp(user.id, payload.code)
        if method == "totp"
        else services.mfa.verify_recovery_code(user.id, payload.code)
    )
    if not verified:
        services.auth_challenge.record_failure(
            payload.challenge_id,
            nonce,
            expected_phase="login",
            expected_method=method,
        )
        _audit_failure(
            services,
            challenge,
            email=user.email,
            client_ip=_client_ip(request),
            method=method,
        )
        raise _invalid_code()
    consumed = services.auth_challenge.consume(
        payload.challenge_id,
        nonce,
        expected_phase="login",
        expected_method=method,
    )
    if consumed is None:
        raise _invalid_challenge()
    services.audit.safe_log_for(
        _actor(challenge, user.email),
        AuditEventType.MFA_VERIFY_SUCCESS,
        entity_type="user",
        entity_id=user.id,
        metadata={"ip": _client_ip(request), "method": method},
    )
    return _finish_login(
        services=services,
        request=request,
        user=user,
        via="mfa",
        audit_metadata={"mfa": True, "method": method},
        identity=identity,
    )


@router.post(
    "/totp/verify",
    response_model=AuthenticatedResponse,
    responses={401: {}, 422: {}, 429: {}},
)
async def verify_totp(
    payload: MFACodeVerifyRequest,
    request: Request,
    services: RequestServices = Depends(get_services),
) -> JSONResponse:
    return await _verify_code("totp", payload, request, services)


@router.post(
    "/recovery/verify",
    response_model=AuthenticatedResponse,
    responses={401: {}, 422: {}, 429: {}},
)
async def verify_recovery_code(
    payload: MFACodeVerifyRequest,
    request: Request,
    services: RequestServices = Depends(get_services),
) -> JSONResponse:
    return await _verify_code("recovery", payload, request, services)


@router.post(
    "/passkeys/begin",
    response_model=dict[str, Any],
    responses={401: {}, 422: {}},
)
async def begin_passkey_authentication(
    payload: PasskeyAuthBeginRequest,
    request: Request,
    services: RequestServices = Depends(get_services),
) -> JSONResponse:
    nonce = _nonce(request)
    challenge = services.auth_challenge.get_valid(
        payload.challenge_id,
        nonce,
        expected_phase="login",
        expected_method="passkey",
    )
    if challenge is None or challenge.user_id is None:
        raise _invalid_challenge()
    passkeys = services.mfa.list_passkeys(challenge.user_id)
    options = webauthn.generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=webauthn.base64url_to_bytes(passkey.credential_id)) for passkey in passkeys
        ],
    )
    persisted = services.auth_challenge.set_webauthn_challenge(
        payload.challenge_id,
        nonce,
        expected_phase="login",
        webauthn_challenge=options.challenge,
    )
    if persisted is None:
        raise _invalid_challenge()
    return JSONResponse(json.loads(webauthn.options_to_json(options)))


@router.post(
    "/passkeys/complete",
    response_model=AuthenticatedResponse,
    responses={401: {}, 422: {}, 429: {}},
)
async def complete_passkey_authentication(
    payload: PasskeyAuthCompleteRequest,
    request: Request,
    services: RequestServices = Depends(get_services),
) -> JSONResponse:
    nonce = _nonce(request)
    challenge = services.auth_challenge.get_valid(
        payload.challenge_id,
        nonce,
        expected_phase="login",
        expected_method="passkey",
    )
    if challenge is None or challenge.user_id is None or challenge.webauthn_challenge is None:
        raise _invalid_challenge()
    user = services.user.get_by_id(challenge.user_id)
    if user is None:
        raise _invalid_challenge()
    identity = _reserve_attempt(services, request, payload.challenge_id)
    credential_id = str(payload.credential.get("id", ""))
    passkey = services.mfa.get_passkey_by_credential_id(credential_id)
    if passkey is None or passkey.user_id != user.id:
        services.auth_challenge.record_failure(
            payload.challenge_id,
            nonce,
            expected_phase="login",
            expected_method="passkey",
        )
        _audit_failure(
            services,
            challenge,
            email=user.email,
            client_ip=_client_ip(request),
            method="passkey",
        )
        raise _invalid_passkey()
    try:
        verification = webauthn.verify_authentication_response(
            credential=payload.credential,
            expected_challenge=challenge.webauthn_challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            credential_public_key=webauthn.base64url_to_bytes(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
        )
    except Exception:
        logger.warning("passkey_auth_failed", user_id=user.id)
        services.auth_challenge.record_failure(
            payload.challenge_id,
            nonce,
            expected_phase="login",
            expected_method="passkey",
        )
        _audit_failure(
            services,
            challenge,
            email=user.email,
            client_ip=_client_ip(request),
            method="passkey",
        )
        raise _invalid_passkey() from None
    consumed = services.auth_challenge.consume(
        payload.challenge_id,
        nonce,
        expected_phase="login",
        expected_method="passkey",
    )
    if consumed is None:
        raise _invalid_challenge()
    services.mfa.update_passkey_sign_count(passkey.id, verification.new_sign_count)
    services.audit.safe_log_for(
        _actor(challenge, user.email),
        AuditEventType.MFA_PASSKEY_USED,
        entity_type="user",
        entity_id=user.id,
        metadata={"ip": _client_ip(request), "passkey_uuid": passkey.uuid},
    )
    return _finish_login(
        services=services,
        request=request,
        user=user,
        via="passkey",
        audit_metadata={"mfa": True, "method": "passkey"},
        identity=identity,
    )
