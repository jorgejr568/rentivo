from __future__ import annotations

import time
from datetime import datetime

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from rentivo.models.audit_log import AuditEventType
from rentivo.services.audit_serializers import serialize_user
from rentivo.settings import settings
from web.analytics import push_event
from web.deps import (
    get_audit_service,
    get_job_service,
    get_known_device_service,
    get_mfa_service,
    get_turnstile_service,
    get_user_service,
    render,
)

logger = structlog.get_logger(__name__)

router = APIRouter()

# Simple in-memory rate limiter for login attempts
_login_attempts: dict[str, list[float]] = {}
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 60

# Rate limiter for MFA verification
_mfa_attempts: dict[str, list[float]] = {}
_MFA_MAX_ATTEMPTS = 5
_MFA_LOCKOUT_SECONDS = 300


def _is_rate_limited(ip: str) -> bool:
    """Check if an IP is rate-limited. Returns True if locked out."""
    now = time.monotonic()
    attempts = _login_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < _LOCKOUT_SECONDS]
    _login_attempts[ip] = attempts
    return len(attempts) >= _MAX_ATTEMPTS


def _record_failed_attempt(ip: str) -> None:
    """Record a failed login attempt for rate limiting."""
    now = time.monotonic()
    attempts = _login_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < _LOCKOUT_SECONDS]
    attempts.append(now)
    _login_attempts[ip] = attempts


def _clear_attempts(ip: str) -> None:
    """Clear failed attempts after successful login."""
    _login_attempts.pop(ip, None)


def _is_mfa_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    attempts = _mfa_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < _MFA_LOCKOUT_SECONDS]
    _mfa_attempts[ip] = attempts
    return len(attempts) >= _MFA_MAX_ATTEMPTS


def _record_mfa_failed(ip: str) -> None:
    now = time.monotonic()
    attempts = _mfa_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < _MFA_LOCKOUT_SECONDS]
    attempts.append(now)
    _mfa_attempts[ip] = attempts


def _clear_mfa_attempts(ip: str) -> None:
    _mfa_attempts.pop(ip, None)


def _check_and_send_new_device_email(request: Request, user) -> None:
    user_agent = request.headers.get("user-agent", "")
    client_ip = request.client.host if request.client else "unknown"
    kd_service = get_known_device_service(request)
    if kd_service.register_login(user.id, user_agent, client_ip):
        return
    forgot_url = f"{settings.public_app_url.rstrip('/')}/forgot-password"
    get_job_service(request).enqueue(
        "email.send",
        {
            "event": "new_device_login",
            "to_email": user.email,
            "ctx": {
                "email": user.email,
                "logged_in_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "source_ip": client_ip,
                "user_agent": user_agent,
                "reset_url": forgot_url,
            },
        },
        source="web",
        actor_id=user.id,
        actor_username=user.email,
    )


@router.get("/signup")
async def signup_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/billings/", status_code=302)
    return render(request, "signup.html")


@router.post("/signup")
async def signup(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/billings/", status_code=302)

    form = await request.form()
    email = str(form.get("email", "")).strip()
    password = str(form.get("password", ""))
    confirm_password = str(form.get("confirm_password", ""))

    turnstile_token = str(form.get("cf-turnstile-response", ""))
    client_ip = request.client.host if request.client else "unknown"
    turnstile = get_turnstile_service(request)
    if not await turnstile.verify(turnstile_token, client_ip):
        logger.warning("signup_turnstile_failed", email=email, client_ip=client_ip)
        return render(request, "signup.html", {"error": "Verificação de segurança falhou. Tente novamente."})

    if not email or not password:
        logger.warning("signup_rejected", reason="empty_fields")
        return render(request, "signup.html", {"error": "Preencha todos os campos."})

    if password != confirm_password:
        logger.warning("signup_rejected", reason="password_mismatch", email=email)
        return render(request, "signup.html", {"error": "As senhas não coincidem."})

    user_service = get_user_service(request)
    try:
        user = user_service.register_user(email, password)
    except ValueError:
        logger.warning("signup_rejected", reason="duplicate_email", email=email)
        return render(request, "signup.html", {"error": "E-mail já cadastrado."})

    request.session.clear()
    request.session["user_id"] = user.id
    request.session["email"] = user.email
    logger.info("user_signed_up", email=user.email)

    # /signup is public, so request.state.actor is ANON_ACTOR. Build a local
    # WebActor from the just-created user so both the audit row and the
    # welcome email job record who completed the signup.
    from web.context import WebActor

    signup_actor = WebActor(user_id=user.id, email=user.email)

    audit = get_audit_service(request)
    audit.safe_log_for(
        signup_actor,
        AuditEventType.USER_SIGNUP,
        entity_type="user",
        entity_id=user.id,
        new_state=serialize_user(user),
    )

    push_event(request, {"event": "rentivo_signup_completed"})

    pix_setup_url = f"{settings.public_app_url.rstrip('/')}/security/pix"
    get_job_service(request).enqueue_for(
        signup_actor,
        "email.send",
        {
            "event": "welcome",
            "to_email": user.email,
            "ctx": {"email": user.email, "pix_setup_url": pix_setup_url},
        },
    )
    return RedirectResponse("/billings/", status_code=302)


@router.get("/login")
async def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/billings/", status_code=302)
    return render(request, "login.html")


@router.post("/login")
async def login(request: Request):
    client_ip = request.client.host if request.client else "unknown"

    if _is_rate_limited(client_ip):
        logger.warning("login_rate_limited", client_ip=client_ip)
        push_event(request, {"event": "rentivo_login_failed", "reason": "rate_limited"})
        return render(
            request,
            "login.html",
            {
                "error": "Muitas tentativas. Aguarde um momento antes de tentar novamente.",
            },
        )

    form = await request.form()
    email = str(form.get("email", "")).strip()
    password = form.get("password", "")
    turnstile_token = str(form.get("cf-turnstile-response", ""))

    turnstile = get_turnstile_service(request)
    if not await turnstile.verify(turnstile_token, client_ip):
        logger.warning("login_turnstile_failed", email=email, client_ip=client_ip)
        return render(request, "login.html", {"error": "Verificação de segurança falhou. Tente novamente."})

    user_service = get_user_service(request)
    user = user_service.authenticate(email, str(password))

    if user is None:
        _record_failed_attempt(client_ip)
        logger.warning("login_failed", email=email, client_ip=client_ip)
        audit = get_audit_service(request)
        audit.safe_log_for(
            request.state.actor,
            AuditEventType.USER_LOGIN_FAILED,
            entity_type="user",
            new_state={"email": email},
            metadata={"ip": client_ip},
        )
        push_event(request, {"event": "rentivo_login_failed", "reason": "bad_credentials"})
        return render(request, "login.html", {"error": "E-mail ou senha inválidos."})

    _clear_attempts(client_ip)

    # Check if user has MFA enabled
    mfa_service = get_mfa_service(request)
    has_mfa = mfa_service.has_any_mfa(user.id)

    # /login is public, so request.state.actor is ANON_ACTOR. Build a local
    # WebActor from the just-authenticated user for the post-auth audit rows.
    from web.context import WebActor

    login_actor = WebActor(user_id=user.id, email=user.email)

    if has_mfa:
        # Don't fully authenticate yet — redirect to MFA verification
        request.session.clear()
        request.session["mfa_pending_user_id"] = user.id
        request.session["mfa_pending_email"] = user.email
        logger.info("mfa_verification_required", email=user.email, user_id=user.id)

        audit = get_audit_service(request)
        audit.safe_log_for(
            login_actor,
            AuditEventType.MFA_CHALLENGE_ISSUED,
            entity_type="user",
            entity_id=user.id,
            metadata={"ip": client_ip},
        )

        return RedirectResponse("/mfa-verify", status_code=302)

    # No MFA — complete login
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["email"] = user.email
    logger.info("user_logged_in", email=user.email, user_id=user.id)

    # Check if MFA setup is required by org enforcement
    if mfa_service.user_requires_mfa_setup(user.id):
        request.session["mfa_setup_required"] = True

    audit = get_audit_service(request)
    audit.safe_log_for(
        login_actor,
        AuditEventType.USER_LOGIN,
        entity_type="user",
        entity_id=user.id,
        new_state={"user_id": user.id, "email": user.email},
        metadata={"ip": client_ip},
    )

    push_event(request, {"event": "rentivo_login_success", "via": "password"})
    _check_and_send_new_device_email(request, user)
    return RedirectResponse("/billings/", status_code=302)


# --- MFA Verification ---


@router.get("/mfa-verify")
async def mfa_verify_page(request: Request):
    if not request.session.get("mfa_pending_user_id"):
        return RedirectResponse("/login", status_code=302)

    user_id = request.session["mfa_pending_user_id"]
    mfa_service = get_mfa_service(request)
    has_passkeys = len(mfa_service.list_passkeys(user_id)) > 0

    return render(
        request,
        "mfa_verify.html",
        {
            "has_passkeys": has_passkeys,
        },
    )


@router.post("/mfa-verify")
async def mfa_verify(request: Request):
    user_id = request.session.get("mfa_pending_user_id")
    email = request.session.get("mfa_pending_email")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    client_ip = request.client.host if request.client else "unknown"

    if _is_mfa_rate_limited(client_ip):
        logger.warning("mfa_rate_limited", client_ip=client_ip)
        return render(
            request,
            "mfa_verify.html",
            {
                "error": "Muitas tentativas. Aguarde alguns minutos.",
                "has_passkeys": False,
            },
        )

    form = await request.form()
    code = str(form.get("code", "")).strip()
    method = str(form.get("method", "totp"))

    mfa_service = get_mfa_service(request)

    if method == "recovery":
        verified = mfa_service.verify_recovery_code(user_id, code)
    else:
        verified = mfa_service.verify_totp(user_id, code)

    # During MFA verification the session has mfa_pending_user_id but NOT
    # user_id - request.state.actor is ANON_ACTOR. Build a local actor.
    from web.context import WebActor

    verify_actor = WebActor(user_id=user_id, email=email or "")

    if not verified:
        _record_mfa_failed(client_ip)
        audit = get_audit_service(request)
        audit.safe_log_for(
            verify_actor,
            AuditEventType.MFA_VERIFY_FAILED,
            entity_type="user",
            entity_id=user_id,
            metadata={"ip": client_ip, "method": method},
        )

        push_event(request, {"event": "rentivo_mfa_verify_failed"})
        has_passkeys = len(mfa_service.list_passkeys(user_id)) > 0
        return render(
            request,
            "mfa_verify.html",
            {
                "error": "Código inválido. Tente novamente.",
                "has_passkeys": has_passkeys,
            },
        )

    # MFA verified — complete login
    _clear_mfa_attempts(client_ip)
    request.session.clear()
    request.session["user_id"] = user_id
    request.session["email"] = email

    if mfa_service.user_requires_mfa_setup(user_id):
        request.session["mfa_setup_required"] = True

    audit = get_audit_service(request)
    audit.safe_log_for(
        verify_actor,
        AuditEventType.MFA_VERIFY_SUCCESS,
        entity_type="user",
        entity_id=user_id,
        metadata={"ip": client_ip, "method": method},
    )
    audit.safe_log_for(
        verify_actor,
        AuditEventType.USER_LOGIN,
        entity_type="user",
        entity_id=user_id,
        new_state={"user_id": user_id, "email": email},
        metadata={"ip": client_ip, "mfa": True},
    )

    logger.info("mfa_verified", email=email, method=method)
    push_event(request, {"event": "rentivo_login_success", "via": "mfa"})
    user = get_user_service(request).get_by_id(user_id)
    if user is not None:
        _check_and_send_new_device_email(request, user)
    return RedirectResponse("/billings/", status_code=302)


@router.get("/change-password")
async def change_password_redirect(request: Request):
    return RedirectResponse("/security", status_code=302)


@router.post("/logout")
async def logout(request: Request):
    user_id = request.session.get("user_id")
    email = request.session.get("email")

    audit = get_audit_service(request)
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.USER_LOGOUT,
        entity_type="user",
        entity_id=user_id,
        new_state={"email": email},
    )

    request.session.clear()
    push_event(request, {"event": "rentivo_logout"})
    logger.info("user_logged_out", email=email)
    return RedirectResponse("/login", status_code=302)
