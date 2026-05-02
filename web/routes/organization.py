from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from rentivo.models.audit_log import AuditEventType
from rentivo.models.organization import OrgRole
from rentivo.services.audit_serializers import serialize_invite, serialize_organization
from rentivo.settings import settings
from web.analytics import analytics_hash, push_event
from web.deps import (
    get_audit_service,
    get_authorization_service,
    get_billing_service,
    get_invite_service,
    get_job_service,
    get_mfa_service,
    get_organization_service,
    get_user_service,
    render,
)
from web.flash import flash

logger = structlog.get_logger(__name__)

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
        logger.warning("organization_create_rejected", reason="empty_name")
        flash(request, "Nome é obrigatório.", "danger")
        return RedirectResponse("/organizations/create", status_code=302)

    user_id = request.session.get("user_id")
    service = get_organization_service(request)
    org = service.create_organization(name, user_id)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.ORGANIZATION_CREATE,
        actor_id=user_id,
        actor_username=request.session.get("email", ""),
        source="web",
        entity_type="organization",
        entity_id=org.id,
        entity_uuid=org.uuid,
        new_state=serialize_organization(org),
    )

    flash(request, f"Organização '{org.name}' criada com sucesso!", "success")
    push_event(request, {"event": "rentivo_organization_created", "org_id_hash": analytics_hash(org.uuid)})
    return RedirectResponse(f"/organizations/{org.uuid}", status_code=302)


@router.get("/{org_uuid}")
async def organization_detail(request: Request, org_uuid: str):
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("organization_not_found", org_uuid=org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member:
        logger.warning("organization_access_denied", org_uuid=org_uuid)
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
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("organization_not_found", org_uuid=org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        logger.warning("organization_edit_access_denied", org_uuid=org_uuid)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    return render(request, "organization/edit.html", {"org": org})


@router.post("/{org_uuid}/edit")
async def organization_edit(request: Request, org_uuid: str):
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("organization_not_found", org_uuid=org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        logger.warning("organization_edit_access_denied", org_uuid=org_uuid)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    previous_state = serialize_organization(org)

    form = await request.form()
    org.name = str(form.get("name", "")).strip()
    org.pix_key = str(form.get("pix_key", "")).strip()
    org.pix_merchant_name = str(form.get("pix_merchant_name", "")).strip()
    org.pix_merchant_city = str(form.get("pix_merchant_city", "")).strip()
    if not org.name:
        logger.warning("organization_edit_rejected", org_uuid=org_uuid, reason="empty_name")
        flash(request, "Nome é obrigatório.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}/edit", status_code=302)

    try:
        updated = service.update_organization(org)
    except ValueError as e:
        flash(request, str(e), "danger")
        return RedirectResponse(f"/organizations/{org_uuid}/edit", status_code=302)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.ORGANIZATION_UPDATE,
        actor_id=user_id,
        actor_username=request.session.get("email", ""),
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
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("organization_not_found", org_uuid=org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        logger.warning("organization_delete_access_denied", org_uuid=org_uuid)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    previous_state = serialize_organization(org)
    service.delete_organization(org.id)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.ORGANIZATION_DELETE,
        actor_id=user_id,
        actor_username=request.session.get("email", ""),
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
        logger.warning("organization_not_found", org_uuid=org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        logger.warning("org_member_role_access_denied", org_uuid=org_uuid)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    form = await request.form()
    new_role = str(form.get("role", "")).strip()
    if new_role not in [r.value for r in OrgRole]:
        logger.warning("org_member_role_invalid", org_uuid=org_uuid, member_user_id=member_user_id, role=new_role)
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
        actor_username=request.session.get("email", ""),
        source="web",
        entity_type="organization",
        entity_id=org.id,
        entity_uuid=org.uuid,
        previous_state={"role": old_role},
        new_state={"role": new_role},
    )

    member_user = get_user_service(request).get_by_id(member_user_id)
    if member_user is not None:
        old_label = OrgRole.label(old_role) if old_role else "—"
        new_label = OrgRole.label(new_role)
        get_job_service(request).enqueue(
            "email.send",
            {
                "event": "member_changed",
                "to_email": member_user.email,
                "ctx": {
                    "change_message": f"Sua função mudou de {old_label} para {new_label}.",
                    "org_name": org.name,
                    "actor_email": request.session.get("email", ""),
                },
            },
            source="web",
            actor_id=request.session.get("user_id"),
            actor_username=request.session.get("email", ""),
        )

    flash(request, "Papel atualizado com sucesso!", "success")
    return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)


@router.post("/{org_uuid}/members/{member_user_id}/remove")
async def member_remove(request: Request, org_uuid: str, member_user_id: int):
    service = get_organization_service(request)
    org = service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("organization_not_found", org_uuid=org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        logger.warning("org_member_remove_access_denied", org_uuid=org_uuid)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    if member_user_id == user_id:
        logger.warning("org_member_self_removal_attempted", org_uuid=org_uuid)
        flash(request, "Você não pode remover a si mesmo.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    target_member = service.get_member(org.id, member_user_id)
    old_role = target_member.role if target_member else ""
    service.remove_member(org.id, member_user_id)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.ORGANIZATION_REMOVE_MEMBER,
        actor_id=user_id,
        actor_username=request.session.get("email", ""),
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
    org_service = get_organization_service(request)
    org = org_service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("organization_not_found", org_uuid=org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = org_service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        logger.warning("invite_access_denied", org_uuid=org_uuid)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    role = str(form.get("role", "viewer")).strip()

    if not email:
        logger.warning("invite_rejected", org_uuid=org_uuid, reason="empty_email")
        flash(request, "Informe o e-mail.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    invite_service = get_invite_service(request)
    try:
        invite = invite_service.send_invite(org.id, email, role, user_id)
    except ValueError as e:
        logger.warning("invite_failed", org_uuid=org_uuid, email=email, error=str(e))
        flash(request, str(e), "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    audit = get_audit_service(request)
    if invite:
        audit.safe_log(
            AuditEventType.INVITE_SEND,
            actor_id=user_id,
            actor_username=request.session.get("email", ""),
            source="web",
            entity_type="invite",
            entity_id=invite.id,
            entity_uuid=invite.uuid,
            new_state=serialize_invite(invite),
        )

    inviter_email = request.session.get("email", "")
    invites_url = f"{settings.public_app_url.rstrip('/')}/invites/"
    get_job_service(request).enqueue(
        "email.send",
        {
            "event": "invite_received",
            "to_email": email,
            "ctx": {
                "inviter_email": inviter_email,
                "org_name": org.name,
                "role_label": OrgRole.label(role),
                "invites_url": invites_url,
            },
        },
        source="web",
        actor_id=user_id,
        actor_username=request.session.get("email", ""),
    )

    flash(request, f"Convite enviado para '{email}'!", "success")
    push_event(request, {"event": "rentivo_invite_sent", "org_id_hash": analytics_hash(org_uuid)})
    return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)


@router.post("/{org_uuid}/toggle-mfa")
async def organization_toggle_mfa(request: Request, org_uuid: str):
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
        actor_username=request.session.get("email", ""),
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
    org_service = get_organization_service(request)
    org = org_service.get_by_uuid(org_uuid)
    if not org:
        logger.warning("organization_not_found", org_uuid=org_uuid)
        flash(request, "Organização não encontrada.", "danger")
        return RedirectResponse("/organizations/", status_code=302)

    user_id = request.session.get("user_id")
    member = org_service.get_member(org.id, user_id)
    if not member or member.role != OrgRole.ADMIN.value:
        logger.warning("transfer_billing_access_denied", org_uuid=org_uuid)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    form = await request.form()
    billing_uuid = str(form.get("billing_uuid", "")).strip()
    if not billing_uuid:
        logger.warning("transfer_billing_rejected", org_uuid=org_uuid, reason="no_billing_selected")
        flash(request, "Selecione uma cobrança.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)
    billing = billing_service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("billing_not_found_for_transfer", billing_uuid=billing_uuid, org_uuid=org_uuid)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    if not auth_service.can_transfer_billing(user_id, billing):
        logger.warning("transfer_billing_denied", billing_uuid=billing_uuid)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    previous_owner = {"owner_type": billing.owner_type, "owner_id": billing.owner_id}
    try:
        billing_service.transfer_to_organization(billing.id, org.id)
    except ValueError as e:
        logger.warning("transfer_billing_failed", billing_uuid=billing_uuid, org_uuid=org_uuid, error=str(e))
        flash(request, str(e), "danger")
        return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.BILLING_TRANSFER,
        actor_id=user_id,
        actor_username=request.session.get("email", ""),
        source="web",
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        previous_state=previous_owner,
        new_state={"owner_type": "organization", "owner_id": org.id},
    )

    from web.routes.billing import _notify_billing_transferred

    _notify_billing_transferred(request, billing, previous_owner, org.id, user_id)

    flash(request, "Cobrança transferida com sucesso!", "success")
    return RedirectResponse(f"/organizations/{org_uuid}", status_code=302)
