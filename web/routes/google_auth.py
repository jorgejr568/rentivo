from __future__ import annotations

import secrets

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError

from rentivo.models.audit_log import AuditEventType
from rentivo.models.user import User
from rentivo.services.audit_serializers import serialize_user
from rentivo.settings import settings
from web.analytics import push_event
from web.context import actor_for
from web.deps import render

logger = structlog.get_logger(__name__)

router = APIRouter()

_GOOGLE_LOGIN_ERROR = "Não foi possível entrar com o Google. Tente novamente."


@router.get("/auth/google/login")
async def google_login(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/billings/", status_code=302)

    service = request.state.services.google_auth
    if not service.is_enabled:
        raise HTTPException(status_code=404)

    state = secrets.token_urlsafe(32)
    request.session["google_oauth_state"] = state
    return RedirectResponse(service.build_authorization_url(state), status_code=302)


@router.get("/auth/google/callback")
async def google_callback(request: Request):
    service = request.state.services.google_auth
    if not service.is_enabled:
        raise HTTPException(status_code=404)

    expected_state = request.session.pop("google_oauth_state", "")
    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    error = request.query_params.get("error", "")

    if error or not code or not expected_state or not secrets.compare_digest(state, expected_state):
        logger.warning("google_callback_rejected", oauth_error=error, has_code=bool(code))
        return render(request, "login.html", {"error": _GOOGLE_LOGIN_ERROR})

    info = await service.exchange_code(code)
    if info is None:
        return render(request, "login.html", {"error": _GOOGLE_LOGIN_ERROR})
    if not info.email_verified:
        logger.warning("google_email_not_verified")
        return render(
            request,
            "login.html",
            {"error": "Seu e-mail do Google não está verificado. Verifique-o e tente novamente."},
        )

    user_service = request.state.services.user
    user = user_service.get_by_email(info.email)
    is_new = user is None
    if user is None:
        user = _signup_google_user(request, info.email)
        if user is None:
            return render(request, "login.html", {"error": _GOOGLE_LOGIN_ERROR})

    response = _finish_login(request, user)
    if is_new:
        push_event(request, {"event": "rentivo_signup_completed", "via": "google"})
    return response


def _signup_google_user(request: Request, email: str) -> User | None:
    user_service = request.state.services.user
    try:
        user = user_service.register_google_user(email)
    except ValueError, IntegrityError:
        # Race: a concurrent callback created the account between our
        # get_by_email miss and the insert. Re-fetch and log them in.
        return user_service.get_by_email(email)

    signup_actor = actor_for(user.id, user.email)
    logger.info("google_user_signed_up", email=user.email)

    request.state.services.audit.safe_log_for(
        signup_actor,
        AuditEventType.USER_SIGNUP,
        entity_type="user",
        entity_id=user.id,
        new_state=serialize_user(user),
        metadata={"method": "google"},
    )

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
    return user


def _finish_login(request: Request, user: User) -> RedirectResponse:
    """Post-credential half of POST /login (web/auth.py), for the Google flow.

    Deliberately mirrors — not refactors — the password flow: that one
    interleaves rate limiting and Turnstile, so sharing code would tangle it.
    The MFA gate is identical: with any MFA enrolled only mfa_pending_user_id
    enters the session, and /mfa-verify (TOTP, recovery, passkey) takes over.
    """
    client_ip = request.client.host if request.client else "unknown"
    mfa_service = request.state.services.mfa
    audit = request.state.services.audit
    login_actor = actor_for(user.id, user.email)

    if mfa_service.has_any_mfa(user.id):
        request.session.clear()
        request.session["mfa_pending_user_id"] = user.id
        request.session["mfa_pending_email"] = user.email
        logger.info("mfa_verification_required", email=user.email, user_id=user.id)
        audit.safe_log_for(
            login_actor,
            AuditEventType.MFA_CHALLENGE_ISSUED,
            entity_type="user",
            entity_id=user.id,
            metadata={"ip": client_ip, "method": "google"},
        )
        return RedirectResponse("/mfa-verify", status_code=302)

    request.session.clear()
    request.session["user_id"] = user.id
    request.session["email"] = user.email
    logger.info("user_logged_in", email=user.email, user_id=user.id, method="google")

    if mfa_service.user_requires_mfa_setup(user.id):
        request.session["mfa_setup_required"] = True

    audit.safe_log_for(
        login_actor,
        AuditEventType.USER_LOGIN,
        entity_type="user",
        entity_id=user.id,
        new_state={"user_id": user.id, "email": user.email},
        metadata={"ip": client_ip, "method": "google"},
    )
    push_event(request, {"event": "rentivo_login_success", "via": "google"})
    request.state.services.known_device.notify_if_new(
        user=user,
        user_agent=request.headers.get("user-agent", ""),
        client_ip=client_ip,
        job_service=request.state.services.job,
    )
    return RedirectResponse("/billings/", status_code=302)
