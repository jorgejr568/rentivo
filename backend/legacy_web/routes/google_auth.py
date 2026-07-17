from __future__ import annotations

import secrets

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError

from legacy_web.analytics import push_event
from legacy_web.context import actor_for
from legacy_web.deps import render
from legacy_web.login_flow import begin_mfa_challenge, complete_login
from rentivo.models.audit_log import AuditEventType
from rentivo.models.user import User
from rentivo.services.audit_serializers import serialize_user
from rentivo.settings import settings

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

    client_ip = request.client.host if request.client else "unknown"
    if request.state.services.mfa.has_any_mfa(user.id):
        response = begin_mfa_challenge(request, user, client_ip=client_ip, metadata={"method": "google"})
    else:
        response = complete_login(request, user, via="google", client_ip=client_ip, metadata={"method": "google"})
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
