from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from rentivo.models.audit_log import AuditEventType
from web.analytics import analytics_hash, push_event
from web.deps import get_audit_service, get_invite_service, get_mfa_service, render
from web.flash import flash

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/invites")


@router.get("/")
async def invite_list(request: Request):
    user_id = request.session.get("user_id")
    service = get_invite_service(request)
    invites = service.list_pending(user_id)

    return render(request, "invite/list.html", {"invites": invites})


@router.post("/{invite_uuid}/accept")
async def invite_accept(request: Request, invite_uuid: str):
    user_id = request.session.get("user_id")
    service = get_invite_service(request)
    try:
        service.accept_invite(invite_uuid, user_id)
    except ValueError as e:
        logger.warning("invite_accept_failed", invite_uuid=invite_uuid, error=str(e))
        flash(request, str(e), "danger")
        return RedirectResponse("/invites/", status_code=302)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.INVITE_ACCEPT,
        actor_id=user_id,
        actor_username=request.session.get("email", ""),
        source="web",
        entity_type="invite",
        entity_uuid=invite_uuid,
        previous_state={"status": "pending"},
        new_state={"status": "accepted"},
    )

    # Check if user now needs MFA setup (accepted invite from enforcing org)
    mfa_service = get_mfa_service(request)
    if mfa_service.user_requires_mfa_setup(user_id):
        request.session["mfa_setup_required"] = True

    flash(request, "Convite aceito!", "success")
    push_event(request, {"event": "rentivo_invite_accepted", "invite_uuid_hash": analytics_hash(invite_uuid)})
    return RedirectResponse("/invites/", status_code=302)


@router.post("/{invite_uuid}/decline")
async def invite_decline(request: Request, invite_uuid: str):
    user_id = request.session.get("user_id")
    service = get_invite_service(request)
    try:
        service.decline_invite(invite_uuid, user_id)
    except ValueError as e:
        logger.warning("invite_decline_failed", invite_uuid=invite_uuid, error=str(e))
        flash(request, str(e), "danger")
        return RedirectResponse("/invites/", status_code=302)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.INVITE_DECLINE,
        actor_id=user_id,
        actor_username=request.session.get("email", ""),
        source="web",
        entity_type="invite",
        entity_uuid=invite_uuid,
        previous_state={"status": "pending"},
        new_state={"status": "declined"},
    )

    flash(request, "Convite recusado.", "info")
    push_event(request, {"event": "rentivo_invite_declined"})
    return RedirectResponse("/invites/", status_code=302)
