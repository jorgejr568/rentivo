from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from legacy_web.analytics import analytics_hash, push_event
from legacy_web.deps import render
from legacy_web.flash import flash, flash_redirect
from rentivo.models.audit_log import AuditEventType

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/invites")


@router.get("/")
async def invite_list(request: Request):
    user_id = request.session.get("user_id")
    service = request.state.services.invite
    invites = service.list_pending(user_id)

    return render(request, "invite/list.html", {"invites": invites})


@router.post("/{invite_uuid}/accept")
async def invite_accept(request: Request, invite_uuid: str):
    user_id = request.session.get("user_id")
    service = request.state.services.invite
    try:
        invite = service.accept_invite(invite_uuid, user_id)
    except ValueError as e:
        logger.warning("invite_accept_failed", invite_uuid=invite_uuid, error=str(e))
        return flash_redirect(request, str(e), "/invites/")

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.INVITE_ACCEPT,
        entity_type="invite",
        entity_uuid=invite_uuid,
        previous_state={"status": "pending"},
        new_state={"status": "accepted"},
    )

    request.state.services.job.enqueue_for(
        request.state.actor,
        "email.send",
        {
            "event": "invite_responded",
            "to_email": invite.invited_by_email,
            "ctx": {
                "invitee_email": invite.invited_email,
                "org_name": invite.organization_name,
                "response_label": "aceitou",
            },
        },
    )

    # Check if user now needs MFA setup (accepted invite from enforcing org)
    mfa_service = request.state.services.mfa
    if mfa_service.user_requires_mfa_setup(user_id):
        request.session["mfa_setup_required"] = True

    flash(request, "Convite aceito!", "success")
    push_event(request, {"event": "rentivo_invite_accepted", "invite_uuid_hash": analytics_hash(invite_uuid)})
    return RedirectResponse("/invites/", status_code=302)


@router.post("/{invite_uuid}/decline")
async def invite_decline(request: Request, invite_uuid: str):
    user_id = request.session.get("user_id")
    service = request.state.services.invite
    try:
        invite = service.decline_invite(invite_uuid, user_id)
    except ValueError as e:
        logger.warning("invite_decline_failed", invite_uuid=invite_uuid, error=str(e))
        return flash_redirect(request, str(e), "/invites/")

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.INVITE_DECLINE,
        entity_type="invite",
        entity_uuid=invite_uuid,
        previous_state={"status": "pending"},
        new_state={"status": "declined"},
    )

    request.state.services.job.enqueue_for(
        request.state.actor,
        "email.send",
        {
            "event": "invite_responded",
            "to_email": invite.invited_by_email,
            "ctx": {
                "invitee_email": invite.invited_email,
                "org_name": invite.organization_name,
                "response_label": "recusou",
            },
        },
    )

    flash(request, "Convite recusado.", "info")
    push_event(request, {"event": "rentivo_invite_declined"})
    return RedirectResponse("/invites/", status_code=302)
