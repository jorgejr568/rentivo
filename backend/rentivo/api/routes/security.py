from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime

import structlog
import webauthn
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from rentivo.api.authentication import allow_mfa_setup, reject_out_of_band_credentials
from rentivo.api.csrf import require_csrf
from rentivo.api.dependencies import get_services, require_login_scope
from rentivo.api.errors import ProblemException, problem
from rentivo.api.principal import Principal
from rentivo.api.routes.auth import _clear_auth_cookies, _client_ip, _delete_cookie, _set_challenge_cookie
from rentivo.api.schemas.security import (
    MFAStatusResponse,
    PasskeyListResponse,
    PasskeyRegistrationBeginResponse,
    PasskeyRegistrationCompleteRequest,
    PasskeyResponse,
    PasswordChangeRequest,
    PixUpdateRequest,
    PixUpdateResponse,
    ProfileResponse,
    RecoveryCodesResponse,
    SecuritySummaryResponse,
    TOTPConfirmRequest,
    TOTPDisableRequest,
    TOTPSetupResponse,
    TOTPStatusResponse,
)
from rentivo.constants.api_scopes import APIScope
from rentivo.models.audit_log import AuditEventType
from rentivo.models.mfa import UserPasskey
from rentivo.services.audit_serializers import serialize_user
from rentivo.services.container import RequestServices
from rentivo.services.mfa_service import LastMFAFactorError
from rentivo.settings import settings

logger = structlog.get_logger(__name__)
router = APIRouter(
    prefix="/security",
    tags=["security"],
    dependencies=[Depends(reject_out_of_band_credentials)],
)

_security_principal = require_login_scope(APIScope.SECURITY_MANAGE)
_account_principal = require_login_scope(APIScope.ACCOUNT_WRITE)

_MFA_CHANGE_LABELS = {
    "totp_enabled": "TOTP ativado",
    "totp_disabled": "TOTP desativado",
    "passkey_registered": "Passkey registrado",
    "passkey_deleted": "Passkey removido",
}


def _profile(user: object) -> ProfileResponse:
    return ProfileResponse(
        email=str(getattr(user, "email")),
        pix_key=str(getattr(user, "pix_key", "") or ""),
        pix_merchant_name=str(getattr(user, "pix_merchant_name", "") or ""),
        pix_merchant_city=str(getattr(user, "pix_merchant_city", "") or ""),
    )


def _passkey(passkey: UserPasskey) -> PasskeyResponse:
    return PasskeyResponse(
        uuid=passkey.uuid,
        name=passkey.name,
        created_at=passkey.created_at,
        last_used_at=passkey.last_used_at,
    )


def _webauthn_user_handle(user_id: int) -> bytes:
    return hmac.new(
        settings.get_secret_key().encode(),
        f"rentivo:webauthn-user:{user_id}".encode(),
        hashlib.sha256,
    ).digest()


def _validation_problem(*, code: str, detail: str, field: str) -> ProblemException:
    return ProblemException(
        problem(
            status=422,
            code=code,
            title="Dados inválidos",
            detail=detail,
            fields={field: detail},
        )
    )


def _conflict(code: str, detail: str) -> ProblemException:
    return ProblemException(problem(status=409, code=code, title="Conflito", detail=detail))


def _send_mfa_changed_email(
    request: Request,
    principal: Principal,
    services: RequestServices,
    change_kind: str,
) -> None:
    try:
        services.job.enqueue_for(
            principal.actor,
            "email.send",
            {
                "event": "mfa_changed",
                "to_email": principal.user.email,
                "ctx": {
                    "email": principal.user.email,
                    "change_label": _MFA_CHANGE_LABELS[change_kind],
                    "changed_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "source_ip": _client_ip(request),
                    "reset_url": f"{settings.public_app_url.rstrip('/')}/forgot-password",
                },
            },
        )
    except Exception:
        logger.exception("mfa_changed_dispatch_failed", user_id=principal.user.id, change_kind=change_kind)


def _summary(principal: Principal, services: RequestServices) -> SecuritySummaryResponse:
    user_id = principal.user.id
    totp_enabled = services.mfa.has_confirmed_totp(user_id)
    return SecuritySummaryResponse(
        profile=_profile(principal.user),
        totp=TOTPStatusResponse(
            enabled=totp_enabled,
            recovery_codes_remaining=(services.mfa.count_unused_recovery_codes(user_id) if totp_enabled else 0),
        ),
        mfa=MFAStatusResponse(
            setup_required=services.mfa.user_requires_mfa_setup(user_id),
            organization_enforced=services.mfa.user_in_enforcing_org(user_id),
        ),
        passkeys=tuple(_passkey(passkey) for passkey in services.mfa.list_passkeys(user_id)),
    )


@router.get("", response_model=SecuritySummaryResponse)
async def security_summary(
    principal: Principal = Depends(_security_principal),
    services: RequestServices = Depends(get_services),
) -> SecuritySummaryResponse:
    return _summary(principal, services)


@router.post("/pix", response_model=PixUpdateResponse)
async def update_pix(
    payload: PixUpdateRequest,
    principal: Principal = Depends(_account_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> PixUpdateResponse:
    previous = principal.user
    try:
        updated = services.user.update_pix(
            principal.user.id,
            payload.pix_key,
            payload.pix_merchant_name,
            payload.pix_merchant_city,
        )
    except ValueError as exc:
        detail = str(exc)
        raise _validation_problem(code="invalid_pix_key", detail=detail, field="pix_key") from None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.USER_UPDATE,
        entity_type="user",
        entity_id=principal.user.id,
        previous_state=serialize_user(previous),
        new_state=serialize_user(updated),
    )
    return PixUpdateResponse(profile=_profile(updated))


@router.post("/change-password", status_code=204)
async def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    principal: Principal = Depends(_account_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    if payload.new_password != payload.confirm_password:
        raise _validation_problem(
            code="validation_error",
            detail="As senhas não coincidem.",
            field="confirm_password",
        )
    if not services.login.change_password(
        principal=principal,
        current_password=payload.current_password,
        new_password=payload.new_password,
    ):
        raise ProblemException.bad_request("incorrect_current_password", "Senha atual incorreta.")
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.USER_CHANGE_PASSWORD,
        entity_type="user",
        entity_id=principal.user.id,
        new_state=serialize_user(principal.user),
    )
    try:
        services.job.enqueue_for(
            principal.actor,
            "email.send",
            {
                "event": "password_changed",
                "to_email": principal.user.email,
                "ctx": {
                    "email": principal.user.email,
                    "changed_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "source_ip": _client_ip(request),
                    "reset_url": f"{settings.public_app_url.rstrip('/')}/forgot-password",
                },
            },
        )
    except Exception:
        logger.exception("password_changed_dispatch_failed", user_id=principal.user.id)
    return Response(status_code=204, headers={"X-Rentivo-Analytics-Event": "rentivo_password_changed"})


@router.post("/totp/setup", response_model=TOTPSetupResponse)
async def setup_totp(
    _allow_mfa_setup: None = Depends(allow_mfa_setup),
    principal: Principal = Depends(_security_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> JSONResponse:
    try:
        totp, provisioning_uri, qr_code_base64 = services.mfa.setup_totp(
            principal.user.id,
            principal.user.email,
        )
    except ValueError as exc:
        raise _conflict("totp_already_enabled", str(exc)) from None
    payload = TOTPSetupResponse(
        secret=totp.secret,
        provisioning_uri=provisioning_uri,
        qr_code_base64=qr_code_base64,
    )
    return JSONResponse(payload.model_dump(mode="json"), headers={"Cache-Control": "no-store"})


@router.post("/totp/confirm", response_model=RecoveryCodesResponse)
async def confirm_totp(
    payload: TOTPConfirmRequest,
    request: Request,
    _allow_mfa_setup: None = Depends(allow_mfa_setup),
    principal: Principal = Depends(_security_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> JSONResponse:
    try:
        recovery_codes = services.mfa.confirm_totp(
            principal.user.id,
            payload.code,
            principal.api_key.uuid,
        )
    except ValueError as exc:
        raise ProblemException.bad_request("invalid_totp_code", str(exc)) from None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.MFA_TOTP_ENABLED,
        entity_type="user",
        entity_id=principal.user.id,
    )
    _send_mfa_changed_email(request, principal, services, "totp_enabled")
    response_payload = RecoveryCodesResponse(recovery_codes=tuple(recovery_codes))
    return JSONResponse(
        response_payload.model_dump(mode="json"),
        headers={
            "Cache-Control": "no-store",
            "X-Rentivo-Analytics-Event": "rentivo_mfa_enabled",
            "X-Rentivo-Analytics-Method": "totp",
        },
    )


@router.post("/totp/disable", status_code=204)
async def disable_totp(
    payload: TOTPDisableRequest,
    request: Request,
    principal: Principal = Depends(_security_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    if services.user.authenticate(principal.user.email, payload.password) is None:
        raise ProblemException.bad_request("incorrect_password", "Senha incorreta.")
    try:
        services.mfa.disable_totp(principal.user.id)
    except LastMFAFactorError:
        raise _conflict(
            "mfa_required_by_organization",
            "Você não pode desativar MFA enquanto pertence a uma organização que exige MFA.",
        ) from None
    except ValueError:
        raise _conflict("totp_not_enabled", "TOTP não está ativado.") from None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.MFA_TOTP_DISABLED,
        entity_type="user",
        entity_id=principal.user.id,
    )
    _send_mfa_changed_email(request, principal, services, "totp_disabled")
    response = Response(status_code=204, headers={"X-Rentivo-Analytics-Event": "rentivo_mfa_disabled"})
    _clear_auth_cookies(response, include_challenge=True)
    return response


@router.post("/recovery-codes/regenerate", response_model=RecoveryCodesResponse)
async def regenerate_recovery_codes(
    principal: Principal = Depends(_security_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> JSONResponse:
    try:
        recovery_codes = services.mfa.regenerate_recovery_codes(principal.user.id)
    except ValueError:
        raise _conflict("totp_required", "TOTP não está ativado.") from None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.MFA_RECOVERY_REGENERATED,
        entity_type="user",
        entity_id=principal.user.id,
    )
    payload = RecoveryCodesResponse(recovery_codes=tuple(recovery_codes))
    return JSONResponse(
        payload.model_dump(mode="json"),
        headers={
            "Cache-Control": "no-store",
            "X-Rentivo-Analytics-Event": "rentivo_recovery_codes_regenerated",
        },
    )


@router.get("/passkeys", response_model=PasskeyListResponse)
async def list_passkeys(
    principal: Principal = Depends(_security_principal),
    services: RequestServices = Depends(get_services),
) -> PasskeyListResponse:
    return PasskeyListResponse(
        items=tuple(_passkey(passkey) for passkey in services.mfa.list_passkeys(principal.user.id))
    )


@router.post("/passkeys/register/begin", response_model=PasskeyRegistrationBeginResponse)
async def begin_passkey_registration(
    _allow_mfa_setup: None = Depends(allow_mfa_setup),
    principal: Principal = Depends(_security_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> JSONResponse:
    existing_passkeys = services.mfa.list_passkeys(principal.user.id)
    options = webauthn.generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=_webauthn_user_handle(principal.user.id),
        user_name=principal.user.email,
        user_display_name=principal.user.email,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=webauthn.base64url_to_bytes(passkey.credential_id))
            for passkey in existing_passkeys
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    issued = services.auth_challenge.issue(
        user_id=principal.user.id,
        phase="passkey_registration",
        allowed_methods=("passkey",),
        webauthn_challenge=options.challenge,
    )
    payload = PasskeyRegistrationBeginResponse(
        challenge_id=issued.challenge.uuid,
        options=json.loads(webauthn.options_to_json(options)),
    )
    response = JSONResponse(
        payload.model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True),
        headers={"Cache-Control": "no-store"},
    )
    _set_challenge_cookie(response, issued.nonce)
    return response


@router.post("/passkeys/register/complete", response_model=PasskeyResponse)
async def complete_passkey_registration(
    payload: PasskeyRegistrationCompleteRequest,
    request: Request,
    _allow_mfa_setup: None = Depends(allow_mfa_setup),
    principal: Principal = Depends(_security_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> JSONResponse:
    nonce = request.cookies.get(settings.challenge_cookie_name, "")
    challenge = services.auth_challenge.get_valid(
        payload.challenge_id,
        nonce,
        expected_phase="passkey_registration",
        expected_method="passkey",
    )
    if challenge is None or challenge.user_id != principal.user.id or challenge.webauthn_challenge is None:
        raise ProblemException.unauthorized(
            "invalid_or_expired_challenge",
            "Desafio de autenticação inválido ou expirado.",
        )
    try:
        verification = webauthn.verify_registration_response(
            credential=payload.credential.model_dump(mode="json", by_alias=True, exclude_unset=True),
            expected_challenge=challenge.webauthn_challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
        )
    except Exception:
        logger.warning("passkey_registration_failed", user_id=principal.user.id)
        raise ProblemException.bad_request(
            "invalid_passkey_registration",
            "Falha na verificação da passkey.",
        ) from None
    consumed = services.auth_challenge.consume(
        payload.challenge_id,
        nonce,
        expected_phase="passkey_registration",
        expected_method="passkey",
    )
    if consumed is None:
        raise ProblemException.unauthorized(
            "invalid_or_expired_challenge",
            "Desafio de autenticação inválido ou expirado.",
        )
    name = payload.name.strip()
    passkey = services.mfa.register_passkey(
        UserPasskey(
            user_id=principal.user.id,
            credential_id=base64.urlsafe_b64encode(verification.credential_id).rstrip(b"=").decode(),
            public_key=base64.urlsafe_b64encode(verification.credential_public_key).rstrip(b"=").decode(),
            sign_count=verification.sign_count,
            name=name,
        ),
        principal.api_key.uuid,
    )
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.MFA_PASSKEY_REGISTERED,
        entity_type="user",
        entity_id=principal.user.id,
        metadata={"passkey_name": name},
    )
    _send_mfa_changed_email(request, principal, services, "passkey_registered")
    response_payload = _passkey(passkey)
    response = JSONResponse(
        response_payload.model_dump(mode="json"),
        headers={
            "Cache-Control": "no-store",
            "X-Rentivo-Analytics-Event": "rentivo_passkey_added",
        },
    )
    _delete_cookie(response, settings.challenge_cookie_name, httponly=True)
    return response


@router.delete("/passkeys/{passkey_uuid}", status_code=204)
async def delete_passkey(
    passkey_uuid: str,
    request: Request,
    principal: Principal = Depends(_security_principal),
    _csrf: None = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    try:
        services.mfa.delete_passkey(passkey_uuid, principal.user.id)
    except LastMFAFactorError:
        raise _conflict(
            "mfa_required_by_organization",
            "Você não pode remover o último fator de MFA exigido pela organização.",
        ) from None
    except ValueError:
        raise ProblemException.not_found() from None
    services.audit.safe_log_for(
        principal.actor,
        AuditEventType.MFA_PASSKEY_DELETED,
        entity_type="user",
        entity_id=principal.user.id,
        metadata={"passkey_uuid": passkey_uuid},
    )
    _send_mfa_changed_email(request, principal, services, "passkey_deleted")
    response = Response(status_code=204, headers={"X-Rentivo-Analytics-Event": "rentivo_passkey_removed"})
    _clear_auth_cookies(response, include_challenge=True)
    return response
