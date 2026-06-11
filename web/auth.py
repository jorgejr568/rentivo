from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from rentivo.models.audit_log import AuditEventType
from rentivo.services.audit_serializers import serialize_user
from rentivo.settings import settings
from web.analytics import push_event
from web.context import actor_for
from web.deps import render
from web.login_flow import begin_mfa_challenge, complete_login

logger = structlog.get_logger(__name__)

router = APIRouter()


class RateLimiter:
    """Sliding-window in-memory rate limiter keyed by an arbitrary string (client IP).

    One class replaces the two hand-rolled dict+function trios that previously
    lived in this module (login attempts and MFA attempts) — same logic,
    different constants.
    """

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}

    def _prune(self, key: str) -> list[float]:
        """Drop entries older than the window; store and return the live list."""
        now = time.monotonic()
        attempts = [t for t in self._attempts.get(key, []) if now - t < self.window_seconds]
        self._attempts[key] = attempts
        return attempts

    def is_limited(self, key: str) -> bool:
        return len(self._prune(key)) >= self.max_attempts

    def record_failure(self, key: str) -> None:
        # _prune stores the pruned list in the dict and returns that same list,
        # so appending here mutates the stored state.
        self._prune(key).append(time.monotonic())

    def clear(self, key: str) -> None:
        self._attempts.pop(key, None)

    def reset(self) -> None:
        """Drop all recorded attempts across all keys (test-isolation helper)."""
        self._attempts.clear()


# Login attempts: 5 per 60s per IP. MFA verification: 5 per 300s per IP.
_login_limiter = RateLimiter(max_attempts=5, window_seconds=60)
_mfa_limiter = RateLimiter(max_attempts=5, window_seconds=300)


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
    turnstile = request.state.services.turnstile
    if not await turnstile.verify(turnstile_token, client_ip):
        logger.warning("signup_turnstile_failed", email=email, client_ip=client_ip)
        return render(request, "signup.html", {"error": "Verificação de segurança falhou. Tente novamente."})

    if not email or not password:
        logger.warning("signup_rejected", reason="empty_fields")
        return render(request, "signup.html", {"error": "Preencha todos os campos."})

    if password != confirm_password:
        logger.warning("signup_rejected", reason="password_mismatch", email=email)
        return render(request, "signup.html", {"error": "As senhas não coincidem."})

    user_service = request.state.services.user
    try:
        user = user_service.register_user(email, password)
    except ValueError:
        logger.warning("signup_rejected", reason="duplicate_email", email=email)
        return render(request, "signup.html", {"error": "E-mail já cadastrado."})

    request.session.clear()
    request.session["user_id"] = user.id
    request.session["email"] = user.email
    logger.info("user_signed_up", email=user.email)

    signup_actor = actor_for(user.id, user.email)

    audit = request.state.services.audit
    audit.safe_log_for(
        signup_actor,
        AuditEventType.USER_SIGNUP,
        entity_type="user",
        entity_id=user.id,
        new_state=serialize_user(user),
    )

    push_event(request, {"event": "rentivo_signup_completed"})

    pix_setup_url = f"{settings.public_app_url.rstrip('/')}/security/pix"
    request.state.services.job.enqueue_for(
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

    if _login_limiter.is_limited(client_ip):
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

    turnstile = request.state.services.turnstile
    if not await turnstile.verify(turnstile_token, client_ip):
        logger.warning("login_turnstile_failed", email=email, client_ip=client_ip)
        return render(request, "login.html", {"error": "Verificação de segurança falhou. Tente novamente."})

    user_service = request.state.services.user
    user = user_service.authenticate(email, str(password))

    if user is None:
        _login_limiter.record_failure(client_ip)
        logger.warning("login_failed", email=email, client_ip=client_ip)
        audit = request.state.services.audit
        audit.safe_log_for(
            request.state.actor,
            AuditEventType.USER_LOGIN_FAILED,
            entity_type="user",
            new_state={"email": email},
            metadata={"ip": client_ip},
        )
        push_event(request, {"event": "rentivo_login_failed", "reason": "bad_credentials"})
        return render(request, "login.html", {"error": "E-mail ou senha inválidos."})

    _login_limiter.clear(client_ip)

    # MFA enrolled? Don't fully authenticate yet — issue the challenge.
    if request.state.services.mfa.has_any_mfa(user.id):
        return begin_mfa_challenge(request, user, client_ip=client_ip)

    return complete_login(request, user, via="password", client_ip=client_ip)


# --- MFA Verification ---


@router.get("/mfa-verify")
async def mfa_verify_page(request: Request):
    if not request.session.get("mfa_pending_user_id"):
        return RedirectResponse("/login", status_code=302)

    user_id = request.session["mfa_pending_user_id"]
    mfa_service = request.state.services.mfa
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

    if _mfa_limiter.is_limited(client_ip):
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

    mfa_service = request.state.services.mfa

    if method == "recovery":
        verified = mfa_service.verify_recovery_code(user_id, code)
    else:
        verified = mfa_service.verify_totp(user_id, code)

    verify_actor = actor_for(user_id, email)

    if not verified:
        _mfa_limiter.record_failure(client_ip)
        audit = request.state.services.audit
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
    _mfa_limiter.clear(client_ip)

    user = request.state.services.user.get_by_id(user_id)
    if user is None:
        # The account vanished between the password step and the MFA step
        # (e.g. deleted by an admin). Abort instead of authenticating a
        # ghost session.
        logger.warning("mfa_verify_user_missing", user_id=user_id)
        request.session.clear()
        return RedirectResponse("/login", status_code=302)

    audit = request.state.services.audit
    audit.safe_log_for(
        verify_actor,
        AuditEventType.MFA_VERIFY_SUCCESS,
        entity_type="user",
        entity_id=user_id,
        metadata={"ip": client_ip, "method": method},
    )

    logger.info("mfa_verified", email=email, method=method)
    return complete_login(request, user, via="mfa", client_ip=client_ip, metadata={"mfa": True})


@router.get("/change-password")
async def change_password_redirect(request: Request):
    return RedirectResponse("/security", status_code=302)


@router.post("/logout")
async def logout(request: Request):
    user_id = request.session.get("user_id")
    email = request.session.get("email")

    audit = request.state.services.audit
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
