from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from rentivo.models.audit_log import AuditEventType
from web.analytics import push_event
from web.deps import get_audit_service, get_password_reset_service, get_turnstile_service, render
from web.flash import flash

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
    turnstile = get_turnstile_service(request)
    if not await turnstile.verify(turnstile_token, client_ip):
        logger.warning("forgot_password_turnstile_failed", email=email, client_ip=client_ip)
        return render(request, "forgot_password.html", {"error": "Verificação de segurança falhou. Tente novamente."})
    if not email:
        return render(request, "forgot_password.html", {"error": "Informe um e-mail."})

    service = get_password_reset_service(request)
    try:
        service.request_reset(email)
    except Exception:
        logger.exception("password_reset_dispatch_failed", email=email)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.USER_PASSWORD_RESET_REQUESTED,
        source="web",
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

    service = get_password_reset_service(request)
    user_id = service.consume(token, new_password=password)
    if user_id is None:
        return render(request, "reset_password.html", {"invalid": True})

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.USER_PASSWORD_RESET_COMPLETED,
        actor_id=user_id,
        source="web",
        entity_type="user",
        entity_id=user_id,
    )
    push_event(request, {"event": "rentivo_password_reset_completed"})

    flash(request, "Senha redefinida com sucesso. Faça login com a nova senha.", "success")
    return RedirectResponse("/login", status_code=302)
