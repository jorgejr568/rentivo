"""Shared post-credential login completion.

Every authentication entry point — password (web/auth.py:login), TOTP and
recovery-code verification (web/auth.py:mfa_verify), passkey verification
(web/routes/security.py:passkey_auth_complete) and Google OAuth
(web/routes/google_auth.py) — funnels through these two primitives once the
credential has been verified. Callers keep their own pre-credential logic
(rate limiting, Turnstile, OAuth state, WebAuthn assertion checks) and their
site-specific audit events.

Signatures are fixed by
docs/superpowers/plans/2026-06-11-thermo-nuclear-remediation-index.md.
``metadata`` on ``complete_login`` is the sanctioned optional extension hook:
it is merged into the USER_LOGIN audit metadata after ``{"ip": client_ip}``
so every call site keeps its historical audit shape (password: ip only;
TOTP/recovery: +mfa; passkey: +mfa+method; google: +method).
"""

from __future__ import annotations

import structlog
from fastapi import Request
from fastapi.responses import RedirectResponse

from rentivo.models.audit_log import AuditEventType
from rentivo.models.user import User
from web.analytics import push_event
from web.context import actor_for

logger = structlog.get_logger(__name__)

POST_LOGIN_URL = "/billings/"
MFA_VERIFY_URL = "/mfa-verify"


def begin_mfa_challenge(
    request: Request,
    user: User,
    *,
    client_ip: str = "unknown",
    metadata: dict | None = None,
) -> RedirectResponse:
    """Half-authenticate: park the user in the MFA-pending session state.

    Used when the primary credential checked out but the user has TOTP or
    passkeys enrolled. Only the ``mfa_pending_*`` keys enter the session;
    /mfa-verify (TOTP, recovery code, passkey) takes over from there.
    """
    request.session.clear()
    request.session["mfa_pending_user_id"] = user.id
    request.session["mfa_pending_email"] = user.email
    logger.info("mfa_verification_required", email=user.email, user_id=user.id)

    request.state.services.audit.safe_log_for(
        actor_for(user.id, user.email),
        AuditEventType.MFA_CHALLENGE_ISSUED,
        entity_type="user",
        entity_id=user.id,
        metadata={"ip": client_ip, **(metadata or {})},
    )
    return RedirectResponse(MFA_VERIFY_URL, status_code=302)


def complete_login(
    request: Request,
    user: User,
    *,
    via: str,
    client_ip: str = "unknown",
    metadata: dict | None = None,
) -> RedirectResponse:
    """Fully authenticate the session after every credential check passed.

    Order is load-bearing: ``session.clear()`` first (drops ``mfa_pending_*``,
    OAuth state and any stale keys), then the auth keys, then the side effects
    (audit, analytics, new-device email) — so the queued analytics event
    survives into the fresh session.
    """
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["email"] = user.email
    logger.info("user_logged_in", email=user.email, user_id=user.id, via=via)

    # Org-level MFA enforcement: flag the session so MFAEnforcementMiddleware
    # routes the user to /security/totp/setup.
    if request.state.services.mfa.user_requires_mfa_setup(user.id):
        request.session["mfa_setup_required"] = True

    request.state.services.audit.safe_log_for(
        actor_for(user.id, user.email),
        AuditEventType.USER_LOGIN,
        entity_type="user",
        entity_id=user.id,
        new_state={"user_id": user.id, "email": user.email},
        metadata={"ip": client_ip, **(metadata or {})},
    )

    push_event(request, {"event": "rentivo_login_success", "via": via})
    request.state.services.known_device.notify_if_new(
        user=user,
        user_agent=request.headers.get("user-agent", ""),
        client_ip=client_ip,
        job_service=request.state.services.job,
    )
    return RedirectResponse(POST_LOGIN_URL, status_code=302)
