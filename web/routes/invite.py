from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from web.deps import get_invite_service, render
from web.flash import flash

logger = logging.getLogger(__name__)

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
        flash(request, str(e), "danger")
        return RedirectResponse("/invites/", status_code=302)
    flash(request, "Convite aceito!", "success")
    return RedirectResponse("/invites/", status_code=302)


@router.post("/{invite_uuid}/decline")
async def invite_decline(request: Request, invite_uuid: str):
    user_id = request.session.get("user_id")
    service = get_invite_service(request)
    try:
        service.decline_invite(invite_uuid, user_id)
    except ValueError as e:
        flash(request, str(e), "danger")
        return RedirectResponse("/invites/", status_code=302)
    flash(request, "Convite recusado.", "info")
    return RedirectResponse("/invites/", status_code=302)
