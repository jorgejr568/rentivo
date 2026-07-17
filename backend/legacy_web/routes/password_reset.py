from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from legacy_web.analytics import push_event
from legacy_web.context import actor_for
from legacy_web.deps import render
from legacy_web.flash import flash
from rentivo.models.audit_log import AuditEventType

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/forgot-password")
async def forgot_password_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/billings/", status_code=302)
    return render(request, "forgot_password.html")


@router.post("/forgot-password")
async def forgot_password(request: Request):
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    turnstile_token = str(form.get("cf-turnstile-response", ""))
    client_ip = request.client.host if request.client else "unknown"
    turnstile = request.state.services.turnstile
    if not await turnstile.verify(turnstile_token, client_ip):
        logger.warning("forgot_password_turnstile_failed", email=email, client_ip=client_ip)
        return render(request, "forgot_password.html", {"error": "Verificação de segurança falhou. Tente novamente."})
    if not email:
        return render(request, "forgot_password.html", {"error": "Informe um e-mail."})

    service = request.state.services.password_reset
    try:
        service.request_reset(email)
    except Exception:
        logger.exception("password_reset_dispatch_failed", email=email)

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.USER_PASSWORD_RESET_REQUESTED,
        entity_type="user",
        new_state={"email": email},
    )
    push_event(request, {"event": "rentivo_password_reset_requested"})
    return render(request, "forgot_password.html", {"sent": True})


@router.get("/reset-password")
async def reset_password_page(request: Request):
    token = request.query_params.get("token", "")
    if not token:
        return render(request, "reset_password.html", {"invalid": True})
    return render(request, "reset_password.html", {"token": token, "invalid": False})


@router.post("/reset-password")
async def reset_password(request: Request):
    form = await request.form()
    token = str(form.get("token", ""))
    password = str(form.get("password", ""))
    confirm = str(form.get("confirm_password", ""))

    if not token:
        return render(request, "reset_password.html", {"invalid": True})

    if not password or password != confirm:
        return render(
            request,
            "reset_password.html",
            {"token": token, "error": "As senhas não coincidem.", "invalid": False},
        )

    service = request.state.services.password_reset
    user_id = service.consume(token, new_password=password)
    if user_id is None:
        return render(request, "reset_password.html", {"invalid": True})

    user = request.state.services.user.get_by_id(user_id)
    reset_actor = actor_for(user_id, user.email if user else None)

    if user is not None:
        request.state.services.job.enqueue_for(
            reset_actor,
            "email.send",
            {
                "event": "password_reset_completed",
                "to_email": user.email,
                "ctx": {
                    "email": user.email,
                    "changed_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "source_ip": request.client.host if request.client else "unknown",
                },
            },
        )

    audit = request.state.services.audit
    audit.safe_log_for(
        reset_actor,
        AuditEventType.USER_PASSWORD_RESET_COMPLETED,
        entity_type="user",
        entity_id=user_id,
    )
    push_event(request, {"event": "rentivo_password_reset_completed"})

    flash(request, "Senha redefinida com sucesso. Faça login com a nova senha.", "success")
    return RedirectResponse("/login", status_code=302)
