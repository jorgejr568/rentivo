from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from landlord.models.organization import OrgRole
from web.deps import (
    get_authorization_service,
    get_billing_service,
    get_invite_service,
    get_organization_service,
    render,
)
from web.flash import flash

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organizations")


@router.get("/")
async def organization_list(request: Request):
    user_id = request.session.get("user_id")
    service = get_organization_service(request)
    orgs = service.list_user_organizations(user_id)
    return render(request, "organization/list.html", {"organizations": orgs})


@router.get("/create")
async def organization_create_form(request: Request):
    return render(request, "organization/create.html")


@router.post("/create")
async def organization_create(request: Request):
    form = await request.form()
    name = str(form.get("name", "")).strip()
    if not name:
        flash(request, "Nome é obrigatório.", "danger")
        return RedirectResponse("/organizations/create", status_code=302)

    user_id = request.session.get("user_id")
    service = get_organization_service(request)
    org = service.create_organization(name, user_id)
    flash(request, f"Organização '{org.name}' criada com sucesso!", "success")
    return RedirectResponse(f"/organizations/{org.uuid}", status_code=302)


@router.get("/{org_uuid}")
async def organization_detail(request: Request, org_uuid: str):
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member:
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    members = service.list_members(org.id)
    billing_service = get_billing_service(request)
    # Get billings owned by this org
    all_billings = billing_service.list_billings_for_user(user_id)
    org_billings = [b for b in all_billings if b.owner_type == "organization" and b.owner_id == org.id]

    invite_service = get_invite_service(request)
    invites = invite_service.list_org_invites(org.id) if member.role == OrgRole.ADMIN.value else []

    return render(request, "organization/detail.html", {
        "org": org,
        "members": members,
        "org_billings": org_billings,
        "invites": invites,
        "member_role": member.role,
        "roles": [r.value for r in OrgRole],
    })


@router.get("/{org_uuid}/edit")
async def organization_edit_form(request: Request, org_uuid: str):
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    return render(request, "organization/edit.html", {"org": org})


@router.post("/{org_uuid}/edit")
async def organization_edit(request: Request, org_uuid: str):
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    form = await request.form()
    org.name = str(form.get("name", "")).strip()
    if not org.name:
        flash(request, "Nome é obrigatório.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}/edit", status_code=302)

    service.update_organization(org)
    flash(request, "Organização atualizada com sucesso!", "success")
    return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)


@router.post("/{org_uuid}/delete")
async def organization_delete(request: Request, org_uuid: str):
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    service.delete_organization(org.id)
    flash(request, f"Organização '{org.name}' excluída.", "success")
    return RedirectResponse("/organizations/", status_code=302)


@router.post("/{org_uuid}/members/{member_user_id}/role")
async def member_change_role(request: Request, org_uuid: str, member_user_id: int):
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    form = await request.form()
    new_role = str(form.get("role", "")).strip()
    if new_role not in [r.value for r in OrgRole]:
        flash(request, "Papel inválido.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    service.update_member_role(org.id, member_user_id, new_role)
    flash(request, "Papel atualizado com sucesso!", "success")
    return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)


@router.post("/{org_uuid}/members/{member_user_id}/remove")
async def member_remove(request: Request, org_uuid: str, member_user_id: int):
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    if member_user_id == user_id:
        flash(request, "Você não pode remover a si mesmo.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    service.remove_member(org.id, member_user_id)
    flash(request, "Membro removido.", "success")
    return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)


@router.post("/{org_uuid}/invite")
async def organization_invite(request: Request, org_uuid: str):
    org_service = get_organization_service(request)
    org = org_service.get_by_uuid(org_uuid)
    if not org:
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = org_service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    form = await request.form()
    username = str(form.get("username", "")).strip()
    role = str(form.get("role", "viewer")).strip()

    if not username:
        flash(request, "Nome de usuário é obrigatório.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    invite_service = get_invite_service(request)
    try:
        invite_service.send_invite(org.id, username, role, user_id)
    except ValueError as e:
        flash(request, str(e), "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    flash(request, f"Convite enviado para '{username}'!", "success")
    return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)


@router.post("/{org_uuid}/transfer-billing")
async def organization_transfer_billing(request: Request, org_uuid: str):
    org_service = get_organization_service(request)
    org = org_service.get_by_uuid(org_uuid)
    if not org:
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = org_service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    form = await request.form()
    billing_uuid = str(form.get("billing_uuid", "")).strip()
    if not billing_uuid:
        flash(request, "Selecione uma cobrança.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)
    billing = billing_service.get_billing_by_uuid(billing_uuid)
    if not billing:
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    if not auth_service.can_transfer_billing(user_id, billing):
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    try:
        billing_service.transfer_to_organization(billing.id, org.id)
    except ValueError as e:
        flash(request, str(e), "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    flash(request, "Cobrança transferida com sucesso!", "success")
    return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)
