from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from rentivo.models.audit_log import AuditEventType
from rentivo.services.audit_serializers import serialize_user
from web.deps import get_audit_service, get_mfa_service, get_user_service, render

logger = logging.getLogger(__name__)

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
    username = str(form.get("username", "")).strip()
    email = str(form.get("email", "")).strip()
    password = str(form.get("password", ""))
    confirm_password = str(form.get("confirm_password", ""))

    if not username or not email or not password:
        logger.warning("Signup rejected: empty fields")
        return render(request, "signup.html", {"error": "Preencha todos os campos."})

    if password != confirm_password:
        logger.warning("Signup rejected: password mismatch for username=%s", username)
        return render(request, "signup.html", {"error": "As senhas não coincidem."})

    user_service = get_user_service(request)
    try:
        user = user_service.register_user(username, email, password)
    except ValueError:
        logger.warning("Signup rejected: duplicate username=%s", username)
        return render(request, "signup.html", {"error": "Nome de usuário já existe."})

    request.session.clear()
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    logger.info("User %s signed up", user.username)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.USER_SIGNUP,
        actor_id=user.id,
        actor_username=user.username,
        source="web",
        entity_type="user",
        entity_id=user.id,
        new_state=serialize_user(user),
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
        logger.warning("Rate-limited login attempt from %s", client_ip)
        return render(
            request,
            "login.html",
            {
                "error": "Muitas tentativas. Aguarde um momento antes de tentar novamente.",
            },
        )

    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    user_service = get_user_service(request)
    user = user_service.authenticate(str(username), str(password))

    if user is None:
        _record_failed_attempt(client_ip)
        logger.warning("Failed login attempt for username=%s from %s", username, client_ip)
        audit = get_audit_service(request)
        audit.safe_log(
            AuditEventType.USER_LOGIN_FAILED,
            source="web",
            entity_type="user",
            new_state={"username": str(username)},
            metadata={"ip": client_ip},
        )
        return render(request, "login.html", {"error": "Usuário ou senha inválidos."})

    _clear_attempts(client_ip)

    # Check if user has MFA enabled
    mfa_service = get_mfa_service(request)
    has_mfa = mfa_service.has_any_mfa(user.id)

    if has_mfa:
        # Don't fully authenticate yet — redirect to MFA verification
        request.session.clear()
        request.session["mfa_pending_user_id"] = user.id
        request.session["mfa_pending_username"] = user.username
        logger.info("MFA verification required for user=%s", user.username)

        audit = get_audit_service(request)
        audit.safe_log(
            AuditEventType.MFA_CHALLENGE_ISSUED,
            actor_id=user.id,
            actor_username=user.username,
            source="web",
            entity_type="user",
            entity_id=user.id,
            metadata={"ip": client_ip},
        )

        return RedirectResponse("/mfa-verify", status_code=302)

    # No MFA — complete login
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    logger.info("User %s logged in", user.username)

    # Check if MFA setup is required by org enforcement
    if mfa_service.user_requires_mfa_setup(user.id):
        request.session["mfa_setup_required"] = True

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.USER_LOGIN,
        actor_id=user.id,
        actor_username=user.username,
        source="web",
        entity_type="user",
        entity_id=user.id,
        new_state={"user_id": user.id, "username": user.username},
        metadata={"ip": client_ip},
    )

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
    username = request.session.get("mfa_pending_username")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    client_ip = request.client.host if request.client else "unknown"

    if _is_mfa_rate_limited(client_ip):
        logger.warning("MFA rate-limited from %s", client_ip)
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

    if not verified:
        _record_mfa_failed(client_ip)
        audit = get_audit_service(request)
        audit.safe_log(
            AuditEventType.MFA_VERIFY_FAILED,
            actor_id=user_id,
            actor_username=username or "",
            source="web",
            entity_type="user",
            entity_id=user_id,
            metadata={"ip": client_ip, "method": method},
        )

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
    request.session["username"] = username

    if mfa_service.user_requires_mfa_setup(user_id):
        request.session["mfa_setup_required"] = True

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.MFA_VERIFY_SUCCESS,
        actor_id=user_id,
        actor_username=username or "",
        source="web",
        entity_type="user",
        entity_id=user_id,
        metadata={"ip": client_ip, "method": method},
    )
    audit.safe_log(
        AuditEventType.USER_LOGIN,
        actor_id=user_id,
        actor_username=username or "",
        source="web",
        entity_type="user",
        entity_id=user_id,
        new_state={"user_id": user_id, "username": username},
        metadata={"ip": client_ip, "mfa": True},
    )

    logger.info("MFA verified for user=%s method=%s", username, method)
    return RedirectResponse("/billings/", status_code=302)


@router.get("/change-password")
async def change_password_redirect(request: Request):
    return RedirectResponse("/security", status_code=302)


@router.post("/logout")
async def logout(request: Request):
    user_id = request.session.get("user_id")
    username = request.session.get("username")

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.USER_LOGOUT,
        actor_id=user_id,
        actor_username=username or "",
        source="web",
        entity_type="user",
        entity_id=user_id,
        new_state={"username": username},
    )

    request.session.clear()
    logger.info("User %s logged out", username)
    return RedirectResponse("/login", status_code=302)
