from __future__ import annotations

import base64
import json
import logging
import time

import webauthn
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from rentivo.models.audit_log import AuditEventType
from rentivo.models.mfa import UserPasskey
from rentivo.settings import settings
from web.deps import get_audit_service, get_mfa_service, get_user_service, render
from web.flash import flash

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security")

WEBAUTHN_CHALLENGE_TIMEOUT = 300  # 5 minutes


@router.get("/")
async def security_settings(request: Request):
    user_id = request.session["user_id"]
    mfa_service = get_mfa_service(request)

    totp = mfa_service.get_totp(user_id)
    has_totp = totp is not None and totp.confirmed
    passkeys = mfa_service.list_passkeys(user_id)
    recovery_count = mfa_service.count_unused_recovery_codes(user_id) if has_totp else 0

    return render(
        request,
        "security/index.html",
        {
            "has_totp": has_totp,
            "passkeys": passkeys,
            "recovery_count": recovery_count,
        },
    )


@router.post("/change-password")
async def change_password(request: Request):
    user_id = request.session["user_id"]
    form = await request.form()
    current_password = str(form.get("current_password", ""))
    new_password = str(form.get("new_password", ""))
    confirm_password = str(form.get("confirm_password", ""))

    mfa_service = get_mfa_service(request)
    totp = mfa_service.get_totp(user_id)
    has_totp = totp is not None and totp.confirmed
    passkeys = mfa_service.list_passkeys(user_id)
    recovery_count = mfa_service.count_unused_recovery_codes(user_id) if has_totp else 0
    ctx = {"has_totp": has_totp, "passkeys": passkeys, "recovery_count": recovery_count}

    if not current_password or not new_password:
        logger.warning("Change password rejected: empty fields for user=%s", request.session.get("username"))
        return render(request, "security/index.html", {**ctx, "password_error": "Preencha todos os campos."})

    if new_password != confirm_password:
        logger.warning("Change password rejected: password mismatch for user=%s", request.session.get("username"))
        return render(request, "security/index.html", {**ctx, "password_error": "As senhas não coincidem."})

    user_service = get_user_service(request)
    username = request.session.get("username", "")
    user = user_service.authenticate(username, current_password)

    if user is None:
        logger.warning("Change password failed: incorrect current password for user=%s", username)
        return render(request, "security/index.html", {**ctx, "password_error": "Senha atual incorreta."})

    user_service.change_password(username, new_password)
    logger.info("Password changed for user=%s", username)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.USER_CHANGE_PASSWORD,
        actor_id=user_id,
        actor_username=username,
        source="web",
        entity_type="user",
        entity_id=user_id,
        new_state={"username": username},
    )

    flash(request, "Senha alterada com sucesso!", "success")
    return RedirectResponse("/security", status_code=302)


@router.get("/totp/setup")
async def totp_setup_page(request: Request):
    user_id = request.session["user_id"]
    username = request.session["username"]
    mfa_service = get_mfa_service(request)

    if mfa_service.has_confirmed_totp(user_id):
        flash(request, "TOTP já está ativado.", "info")
        return RedirectResponse("/security", status_code=302)

    totp_record, provisioning_uri, qr_base64 = mfa_service.setup_totp(user_id, username)

    return render(
        request,
        "security/totp_setup.html",
        {
            "qr_base64": qr_base64,
            "secret": totp_record.secret,
            "mfa_setup_required": request.session.get("mfa_setup_required", False),
        },
    )


@router.post("/totp/confirm")
async def totp_confirm(request: Request):
    user_id = request.session["user_id"]
    form = await request.form()
    code = str(form.get("code", "")).strip()

    mfa_service = get_mfa_service(request)
    try:
        recovery_codes = mfa_service.confirm_totp(user_id, code)
    except ValueError as e:
        flash(request, str(e), "danger")
        return RedirectResponse("/security/totp/setup", status_code=302)

    # Clear MFA enforcement flag
    request.session.pop("mfa_setup_required", None)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.MFA_TOTP_ENABLED,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="user",
        entity_id=user_id,
    )

    return render(
        request,
        "security/recovery_codes.html",
        {
            "recovery_codes": recovery_codes,
        },
    )


@router.post("/totp/disable")
async def totp_disable(request: Request):
    user_id = request.session["user_id"]
    form = await request.form()
    password = str(form.get("password", ""))

    user_service = get_user_service(request)
    username = request.session.get("username", "")
    user = user_service.authenticate(username, password)
    if user is None:
        flash(request, "Senha incorreta.", "danger")
        return RedirectResponse("/security", status_code=302)

    mfa_service = get_mfa_service(request)

    if mfa_service.user_in_enforcing_org(user_id):
        flash(request, "Você não pode desativar MFA enquanto pertence a uma organização que exige MFA.", "danger")
        return RedirectResponse("/security", status_code=302)

    mfa_service.disable_totp(user_id)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.MFA_TOTP_DISABLED,
        actor_id=user_id,
        actor_username=username,
        source="web",
        entity_type="user",
        entity_id=user_id,
    )

    flash(request, "TOTP desativado com sucesso.", "success")
    return RedirectResponse("/security", status_code=302)


@router.post("/recovery-codes/regenerate")
async def regenerate_recovery_codes(request: Request):
    user_id = request.session["user_id"]
    mfa_service = get_mfa_service(request)

    try:
        codes = mfa_service.regenerate_recovery_codes(user_id)
    except ValueError as e:
        flash(request, str(e), "danger")
        return RedirectResponse("/security", status_code=302)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.MFA_RECOVERY_REGENERATED,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="user",
        entity_id=user_id,
    )

    return render(
        request,
        "security/recovery_codes.html",
        {
            "recovery_codes": codes,
        },
    )


# --- Passkey routes ---


@router.post("/passkeys/register/begin")
async def passkey_register_begin(request: Request):
    user_id = request.session["user_id"]
    username = request.session["username"]
    mfa_service = get_mfa_service(request)

    existing_passkeys = mfa_service.list_passkeys(user_id)
    exclude_credentials = [
        PublicKeyCredentialDescriptor(
            id=webauthn.base64url_to_bytes(pk.credential_id),
        )
        for pk in existing_passkeys
    ]

    options = webauthn.generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=str(user_id).encode(),
        user_name=username,
        user_display_name=username,
        exclude_credentials=exclude_credentials,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    request.session["webauthn_register_challenge"] = base64.b64encode(options.challenge).decode()
    request.session["webauthn_register_ts"] = time.time()

    return JSONResponse(json.loads(webauthn.options_to_json(options)))


@router.post("/passkeys/register/complete")
async def passkey_register_complete(request: Request):
    user_id = request.session["user_id"]
    challenge_b64 = request.session.pop("webauthn_register_challenge", "")
    challenge_ts = request.session.pop("webauthn_register_ts", 0)

    if not challenge_b64 or (time.time() - challenge_ts) > WEBAUTHN_CHALLENGE_TIMEOUT:
        return JSONResponse({"error": "Desafio expirado. Tente novamente."}, status_code=400)

    challenge = base64.b64decode(challenge_b64)
    body = await request.json()

    try:
        verification = webauthn.verify_registration_response(
            credential=body,
            expected_challenge=challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
        )
    except Exception as e:
        logger.warning("Passkey registration failed for user=%s: %s", user_id, e)
        return JSONResponse({"error": "Falha na verificação da passkey."}, status_code=400)

    passkey_name = body.get("name", "Minha Passkey")
    credential_id_b64 = base64.urlsafe_b64encode(verification.credential_id).rstrip(b"=").decode()
    public_key_b64 = base64.urlsafe_b64encode(verification.credential_public_key).rstrip(b"=").decode()

    mfa_service = get_mfa_service(request)
    passkey = UserPasskey(
        user_id=user_id,
        credential_id=credential_id_b64,
        public_key=public_key_b64,
        sign_count=verification.sign_count,
        name=passkey_name,
    )
    mfa_service.register_passkey(passkey)

    # Clear MFA enforcement flag if applicable
    request.session.pop("mfa_setup_required", None)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.MFA_PASSKEY_REGISTERED,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="user",
        entity_id=user_id,
        metadata={"passkey_name": passkey_name},
    )

    return JSONResponse({"status": "ok", "name": passkey_name})


@router.post("/passkeys/{passkey_uuid}/delete")
async def passkey_delete(request: Request, passkey_uuid: str):
    user_id = request.session["user_id"]
    mfa_service = get_mfa_service(request)

    try:
        mfa_service.delete_passkey(passkey_uuid, user_id)
    except ValueError as e:
        flash(request, str(e), "danger")
        return RedirectResponse("/security", status_code=302)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.MFA_PASSKEY_DELETED,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="user",
        entity_id=user_id,
        metadata={"passkey_uuid": passkey_uuid},
    )

    flash(request, "Passkey removida.", "success")
    return RedirectResponse("/security", status_code=302)


# --- Passkey Authentication (used from /mfa-verify) ---


@router.post("/passkeys/auth/begin")
async def passkey_auth_begin(request: Request):
    user_id = request.session.get("mfa_pending_user_id")
    if not user_id:
        return JSONResponse({"error": "Sem login pendente"}, status_code=400)

    mfa_service = get_mfa_service(request)
    passkeys = mfa_service.list_passkeys(user_id)

    allow_credentials = [
        PublicKeyCredentialDescriptor(
            id=webauthn.base64url_to_bytes(pk.credential_id),
        )
        for pk in passkeys
    ]

    options = webauthn.generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        allow_credentials=allow_credentials,
    )

    request.session["webauthn_auth_challenge"] = base64.b64encode(options.challenge).decode()
    request.session["webauthn_auth_ts"] = time.time()

    return JSONResponse(json.loads(webauthn.options_to_json(options)))


@router.post("/passkeys/auth/complete")
async def passkey_auth_complete(request: Request):
    user_id = request.session.get("mfa_pending_user_id")
    username = request.session.get("mfa_pending_username")
    if not user_id:
        return JSONResponse({"error": "Sem login pendente"}, status_code=400)

    challenge_b64 = request.session.pop("webauthn_auth_challenge", "")
    challenge_ts = request.session.pop("webauthn_auth_ts", 0)

    if not challenge_b64 or (time.time() - challenge_ts) > WEBAUTHN_CHALLENGE_TIMEOUT:
        return JSONResponse({"error": "Desafio expirado."}, status_code=400)

    challenge = base64.b64decode(challenge_b64)
    body = await request.json()

    client_ip = request.client.host if request.client else "unknown"

    mfa_service = get_mfa_service(request)

    # Find the passkey by credential ID
    credential_id_b64 = body.get("id", "")
    passkey = mfa_service.get_passkey_by_credential_id(credential_id_b64)
    if passkey is None or passkey.user_id != user_id:
        return JSONResponse({"error": "Passkey não encontrada."}, status_code=400)

    try:
        verification = webauthn.verify_authentication_response(
            credential=body,
            expected_challenge=challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            credential_public_key=webauthn.base64url_to_bytes(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
        )
    except Exception as e:
        logger.warning("Passkey auth failed for user=%s: %s", user_id, e)
        audit = get_audit_service(request)
        audit.safe_log(
            AuditEventType.MFA_VERIFY_FAILED,
            actor_id=user_id,
            actor_username=username or "",
            source="web",
            entity_type="user",
            entity_id=user_id,
            metadata={"ip": client_ip, "method": "passkey"},
        )
        return JSONResponse({"error": "Falha na verificação."}, status_code=400)

    mfa_service.update_passkey_sign_count(passkey.id, verification.new_sign_count)

    # Complete login
    request.session.clear()
    request.session["user_id"] = user_id
    request.session["username"] = username

    if mfa_service.user_requires_mfa_setup(user_id):
        request.session["mfa_setup_required"] = True

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.MFA_PASSKEY_USED,
        actor_id=user_id,
        actor_username=username or "",
        source="web",
        entity_type="user",
        entity_id=user_id,
        metadata={"ip": client_ip, "passkey_uuid": passkey.uuid},
    )
    audit.safe_log(
        AuditEventType.USER_LOGIN,
        actor_id=user_id,
        actor_username=username or "",
        source="web",
        entity_type="user",
        entity_id=user_id,
        new_state={"user_id": user_id, "username": username},
        metadata={"ip": client_ip, "mfa": True, "method": "passkey"},
    )

    logger.info("Passkey auth verified for user=%s", username)
    return JSONResponse({"status": "ok", "redirect": "/billings/"})
