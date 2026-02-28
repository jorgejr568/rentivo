from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from rentivo.models.audit_log import AuditEventType
from web.deps import get_audit_service, get_invite_service, get_mfa_service, render
from web.flash import flash

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invites")


@router.get("/")
async def invite_list(request: Request):
    logger.info("GET /invites/ — listing pending invites")
    user_id = request.session.get("user_id")
    service = get_invite_service(request)
    invites = service.list_pending(user_id)
    logger.info("Found %d pending invites for user=%s", len(invites), user_id)
    return render(request, "invite/list.html", {"invites": invites})


@router.post("/{invite_uuid}/accept")
async def invite_accept(request: Request, invite_uuid: str):
    logger.info("POST /invites/%s/accept", invite_uuid)
    user_id = request.session.get("user_id")
    service = get_invite_service(request)
    try:
        service.accept_invite(invite_uuid, user_id)
    except ValueError as e:
        logger.warning("Invite accept failed: uuid=%s user=%s error=%s", invite_uuid, user_id, e)
        flash(request, str(e), "danger")
        return RedirectResponse("/invites/", status_code=302)
    logger.info("Invite accepted: uuid=%s user=%s", invite_uuid, user_id)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.INVITE_ACCEPT,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
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
    return RedirectResponse("/invites/", status_code=302)


@router.post("/{invite_uuid}/decline")
async def invite_decline(request: Request, invite_uuid: str):
    logger.info("POST /invites/%s/decline", invite_uuid)
    user_id = request.session.get("user_id")
    service = get_invite_service(request)
    try:
        service.decline_invite(invite_uuid, user_id)
    except ValueError as e:
        logger.warning("Invite decline failed: uuid=%s user=%s error=%s", invite_uuid, user_id, e)
        flash(request, str(e), "danger")
        return RedirectResponse("/invites/", status_code=302)
    logger.info("Invite declined: uuid=%s user=%s", invite_uuid, user_id)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.INVITE_DECLINE,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="invite",
        entity_uuid=invite_uuid,
        previous_state={"status": "pending"},
        new_state={"status": "declined"},
    )

    flash(request, "Convite recusado.", "info")
    return RedirectResponse("/invites/", status_code=302)
