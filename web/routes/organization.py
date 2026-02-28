from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from rentivo.models.audit_log import AuditEventType
from rentivo.models.organization import OrgRole
from rentivo.services.audit_serializers import serialize_invite, serialize_organization
from web.deps import (
    get_audit_service,
    get_authorization_service,
    get_billing_service,
    get_invite_service,
    get_mfa_service,
    get_organization_service,
    render,
)
from web.flash import flash

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organizations")


@router.get("/")
async def organization_list(request: Request):
    logger.info("GET /organizations/ — listing organizations")
    user_id = request.session.get("user_id")
    service = get_organization_service(request)
    orgs = service.list_user_organizations(user_id)
    logger.info("Found %d organizations for user=%s", len(orgs), user_id)
    return render(request, "organization/list.html", {"organizations": orgs})


@router.get("/create")
async def organization_create_form(request: Request):
    logger.info("GET /organizations/create — rendering form")
    return render(request, "organization/create.html")


@router.post("/create")
async def organization_create(request: Request):
    logger.info("POST /organizations/create — creating organization")
    form = await request.form()
    name = str(form.get("name", "")).strip()
    if not name:
        logger.warning("Organization create rejected: empty name")
        flash(request, "Nome é obrigatório.", "danger")
        return RedirectResponse("/organizations/create", status_code=302)

    user_id = request.session.get("user_id")
    service = get_organization_service(request)
    org = service.create_organization(name, user_id)
    logger.info("Organization created: uuid=%s name=%s by user=%s", org.uuid, org.name, user_id)
    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.ORGANIZATION_CREATE,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="organization",
        entity_id=org.id,
        entity_uuid=org.uuid,
        new_state=serialize_organization(org),
    )

    flash(request, f"Organização '{org.name}' criada com sucesso!", "success")
    return RedirectResponse(f"/organizations/{org.uuid}", status_code=302)


@router.get("/{org_uuid}")
async def organization_detail(request: Request, org_uuid: str):
    logger.info("GET /organizations/%s — loading detail", org_uuid)
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("Organization not found: uuid=%s", org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member:
        logger.warning("Organization access denied: uuid=%s user=%s", org_uuid, user_id)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    members = service.list_members(org.id)
    billing_service = get_billing_service(request)
    # Get billings owned by this org
    all_billings = billing_service.list_billings_for_user(user_id)
    org_billings = [b for b in all_billings if b.owner_type == "organization" and b.owner_id == org.id]

    invite_service = get_invite_service(request)
    invites = invite_service.list_org_invites(org.id) if member.role == OrgRole.ADMIN.value else []

    logger.info(
        "Organization detail loaded: uuid=%s members=%d billings=%d",
        org_uuid,
        len(members),
        len(org_billings),
    )
    return render(
        request,
        "organization/detail.html",
        {
            "org": org,
            "members": members,
            "org_billings": org_billings,
            "invites": invites,
            "member_role": member.role,
            "roles": [r.value for r in OrgRole],
        },
    )


@router.get("/{org_uuid}/edit")
async def organization_edit_form(request: Request, org_uuid: str):
    logger.info("GET /organizations/%s/edit — loading edit form", org_uuid)
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("Organization not found: uuid=%s", org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        logger.warning("Organization edit access denied: uuid=%s user=%s", org_uuid, user_id)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    return render(request, "organization/edit.html", {"org": org})


@router.post("/{org_uuid}/edit")
async def organization_edit(request: Request, org_uuid: str):
    logger.info("POST /organizations/%s/edit — updating organization", org_uuid)
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("Organization not found: uuid=%s", org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        logger.warning("Organization edit access denied: uuid=%s user=%s", org_uuid, user_id)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    previous_state = serialize_organization(org)

    form = await request.form()
    org.name = str(form.get("name", "")).strip()
    if not org.name:
        logger.warning("Organization edit rejected: empty name for uuid=%s", org_uuid)
        flash(request, "Nome é obrigatório.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}/edit", status_code=302)

    updated = service.update_organization(org)
    logger.info("Organization updated: uuid=%s name=%s", org_uuid, org.name)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.ORGANIZATION_UPDATE,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="organization",
        entity_id=updated.id,
        entity_uuid=updated.uuid,
        previous_state=previous_state,
        new_state=serialize_organization(updated),
    )

    flash(request, "Organização atualizada com sucesso!", "success")
    return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)


@router.post("/{org_uuid}/delete")
async def organization_delete(request: Request, org_uuid: str):
    logger.info("POST /organizations/%s/delete — deleting organization", org_uuid)
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("Organization not found: uuid=%s", org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        logger.warning("Organization delete access denied: uuid=%s user=%s", org_uuid, user_id)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    previous_state = serialize_organization(org)
    service.delete_organization(org.id)
    logger.info("Organization deleted: uuid=%s name=%s", org_uuid, org.name)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.ORGANIZATION_DELETE,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="organization",
        entity_id=org.id,
        entity_uuid=org.uuid,
        previous_state=previous_state,
    )

    flash(request, f"Organização '{org.name}' excluída.", "success")
    return RedirectResponse("/organizations/", status_code=302)


@router.post("/{org_uuid}/members/{member_user_id}/role")
async def member_change_role(request: Request, org_uuid: str, member_user_id: int):
    logger.info(
        "POST /organizations/%s/members/%s/role — changing role",
        org_uuid,
        member_user_id,
    )
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("Organization not found: uuid=%s", org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        logger.warning("Member role change access denied: org=%s user=%s", org_uuid, user_id)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    form = await request.form()
    new_role = str(form.get("role", "")).strip()
    if new_role not in [r.value for r in OrgRole]:
        logger.warning("Invalid role %s for org=%s member=%s", new_role, org_uuid, member_user_id)
        flash(request, "Papel inválido.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    target_member = service.get_member(org.id, member_user_id)
    old_role = target_member.role if target_member else ""
    service.update_member_role(org.id, member_user_id, new_role)
    logger.info(
        "Member role changed: org=%s member=%s new_role=%s",
        org_uuid,
        member_user_id,
        new_role,
    )

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.ORGANIZATION_UPDATE_MEMBER_ROLE,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="organization",
        entity_id=org.id,
        entity_uuid=org.uuid,
        previous_state={"role": old_role},
        new_state={"role": new_role},
    )

    flash(request, "Papel atualizado com sucesso!", "success")
    return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)


@router.post("/{org_uuid}/members/{member_user_id}/remove")
async def member_remove(request: Request, org_uuid: str, member_user_id: int):
    logger.info("POST /organizations/%s/members/%s/remove", org_uuid, member_user_id)
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("Organization not found: uuid=%s", org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        logger.warning("Member remove access denied: org=%s user=%s", org_uuid, user_id)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    if member_user_id == user_id:
        logger.warning("Self-removal attempted: org=%s user=%s", org_uuid, user_id)
        flash(request, "Você não pode remover a si mesmo.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    target_member = service.get_member(org.id, member_user_id)
    old_role = target_member.role if target_member else ""
    service.remove_member(org.id, member_user_id)
    logger.info("Member removed: org=%s member=%s", org_uuid, member_user_id)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.ORGANIZATION_REMOVE_MEMBER,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="organization",
        entity_id=org.id,
        entity_uuid=org.uuid,
        previous_state={"org_id": org.id, "user_id": member_user_id, "role": old_role},
    )

    flash(request, "Membro removido.", "success")
    return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)


@router.post("/{org_uuid}/invite")
async def organization_invite(request: Request, org_uuid: str):
    logger.info("POST /organizations/%s/invite — sending invite", org_uuid)
    org_service = get_organization_service(request)
    org = org_service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("Organization not found: uuid=%s", org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = org_service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        logger.warning("Invite access denied: org=%s user=%s", org_uuid, user_id)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    form = await request.form()
    username = str(form.get("username", "")).strip()
    role = str(form.get("role", "viewer")).strip()

    if not username:
        logger.warning("Invite rejected: empty username for org=%s", org_uuid)
        flash(request, "Nome de usuário é obrigatório.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    invite_service = get_invite_service(request)
    try:
        invite = invite_service.send_invite(org.id, username, role, user_id)
    except ValueError as e:
        logger.warning("Invite failed: org=%s username=%s error=%s", org_uuid, username, e)
        flash(request, str(e), "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    logger.info("Invite sent: org=%s username=%s role=%s", org_uuid, username, role)

    audit = get_audit_service(request)
    if invite:
        audit.safe_log(
            AuditEventType.INVITE_SEND,
            actor_id=user_id,
            actor_username=request.session.get("username", ""),
            source="web",
            entity_type="invite",
            entity_id=invite.id,
            entity_uuid=invite.uuid,
            new_state=serialize_invite(invite),
        )

    flash(request, f"Convite enviado para '{username}'!", "success")
    return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)


@router.post("/{org_uuid}/toggle-mfa")
async def organization_toggle_mfa(request: Request, org_uuid: str):
    logger.info("POST /organizations/%s/toggle-mfa", org_uuid)
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

    new_value = not org.enforce_mfa
    org_service.set_enforce_mfa(org.id, new_value)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.ORGANIZATION_UPDATE_MFA,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="organization",
        entity_id=org.id,
        entity_uuid=org.uuid,
        previous_state={"enforce_mfa": org.enforce_mfa},
        new_state={"enforce_mfa": new_value},
    )

    status = "ativada" if new_value else "desativada"
    flash(request, f"Exigência de MFA {status}.", "success")

    # If enabling MFA, check if the admin themselves needs to set up MFA
    if new_value:
        mfa_service = get_mfa_service(request)
        if not mfa_service.has_any_mfa(user_id):
            request.session["mfa_setup_required"] = True

    return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)


@router.post("/{org_uuid}/transfer-billing")
async def organization_transfer_billing(request: Request, org_uuid: str):
    logger.info("POST /organizations/%s/transfer-billing", org_uuid)
    org_service = get_organization_service(request)
    org = org_service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("Organization not found: uuid=%s", org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = org_service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        logger.warning("Transfer billing access denied: org=%s user=%s", org_uuid, user_id)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    form = await request.form()
    billing_uuid = str(form.get("billing_uuid", "")).strip()
    if not billing_uuid:
        logger.warning("Transfer billing rejected: no billing selected for org=%s", org_uuid)
        flash(request, "Selecione uma cobrança.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)
    billing = billing_service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("Billing not found for transfer: billing=%s org=%s", billing_uuid, org_uuid)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    if not auth_service.can_transfer_billing(user_id, billing):
        logger.warning("Transfer billing denied: billing=%s user=%s", billing_uuid, user_id)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    try:
        billing_service.transfer_to_organization(billing.id, org.id)
    except ValueError as e:
        logger.warning(
            "Transfer billing failed: billing=%s org=%s error=%s",
            billing_uuid,
            org_uuid,
            e,
        )
        flash(request, str(e), "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    logger.info("Billing transferred: billing=%s org=%s", billing_uuid, org_uuid)
    flash(request, "Cobrança transferida com sucesso!", "success")
    return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)
