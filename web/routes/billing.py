from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from rentivo.models.audit_log import AuditEventType
from rentivo.models.billing import BillingItem, ItemType
from rentivo.services.audit_serializers import serialize_billing
from web.analytics import analytics_hash, push_event
from web.deps import (
    get_audit_service,
    get_authorization_service,
    get_bill_service,
    get_billing_service,
    get_organization_service,
    get_pix_service,
    render,
)
from web.flash import flash
from web.forms import parse_brl, parse_formset

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/billings")


@router.get("/")
async def billing_list(request: Request):
    service = get_billing_service(request)
    pix_service = get_pix_service(request)
    user_id = request.session.get("user_id")
    billings = service.list_billings_for_user(user_id)
    billings_needing_pix = [b for b in billings if pix_service.billing_needs_setup(b)]
    user_pix_incomplete = pix_service.owner_needs_setup("user", user_id) if user_id else False
    return render(
        request,
        "billing/list.html",
        {
            "billings": billings,
            "billings_needing_pix": billings_needing_pix,
            "user_pix_incomplete": user_pix_incomplete,
        },
    )


@router.get("/create")
async def billing_create_form(request: Request):
    return render(request, "billing/create.html")


@router.post("/create")
async def billing_create(request: Request):
    form = await request.form()
    name = str(form.get("name", "")).strip()
    description = str(form.get("description", "")).strip()
    pix_key = str(form.get("pix_key", "")).strip()
    pix_merchant_name = str(form.get("pix_merchant_name", "")).strip()
    pix_merchant_city = str(form.get("pix_merchant_city", "")).strip()

    if not name:
        logger.warning("billing_create_rejected", reason="empty_name")
        flash(request, "Nome é obrigatório.", "danger")
        return RedirectResponse("/billings/create", status_code=302)

    items_data = parse_formset(dict(form), "items")
    items: list[BillingItem] = []
    for row in items_data:
        desc = row.get("description", "").strip()
        if not desc:
            continue
        try:
            item_type = ItemType(row.get("item_type", "fixed"))
        except ValueError:
            item_type = ItemType.FIXED
        amount = 0
        if item_type == ItemType.FIXED:
            amount = parse_brl(row.get("amount", "")) or 0
        items.append(BillingItem(description=desc, amount=amount, item_type=item_type))

    if not items:
        logger.warning("billing_create_rejected", reason="no_items")
        flash(request, "Adicione pelo menos um item.", "danger")
        return RedirectResponse("/billings/create", status_code=302)

    service = get_billing_service(request)
    user_id = request.session.get("user_id", 0)
    organization_id = str(form.get("organization_id", "")).strip()
    if organization_id:
        owner_type = "organization"
        owner_id = int(organization_id)
    else:
        owner_type = "user"
        owner_id = user_id
    try:
        billing = service.create_billing(
            name,
            description,
            items,
            pix_key=pix_key,
            pix_merchant_name=pix_merchant_name,
            pix_merchant_city=pix_merchant_city,
            owner_type=owner_type,
            owner_id=owner_id,
        )
    except ValueError as e:
        flash(request, str(e), "danger")
        return RedirectResponse("/billings/create", status_code=302)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.BILLING_CREATE,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        new_state=serialize_billing(billing),
    )

    flash(request, f"Cobrança '{billing.name}' criada com sucesso!", "success")
    push_event(
        request,
        {
            "event": "rentivo_billing_created",
            "billing_uuid_hash": analytics_hash(billing.uuid),
            "item_count": len(billing.items),
            "has_pix": bool(billing.pix_key),
        },
    )
    return RedirectResponse(f"/billings/{billing.uuid}", status_code=302)


@router.get("/{billing_uuid}")
async def billing_detail(request: Request, billing_uuid: str):
    billing_service = get_billing_service(request)
    bill_service = get_bill_service(request)
    auth_service = get_authorization_service(request)

    billing = billing_service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("billing_not_found", billing_uuid=billing_uuid)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    user_id = request.session.get("user_id")
    if not auth_service.can_view_billing(user_id, billing):
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse("/", status_code=302)

    role = auth_service.get_role_for_billing(user_id, billing)

    if billing.id is None:
        logger.error("billing_missing_id", billing_uuid=billing_uuid)
        flash(request, "Cobrança inválida.", "danger")
        return RedirectResponse("/", status_code=302)

    bills = bill_service.list_bills(billing.id)

    # Load user's orgs for transfer dropdown
    org_service = get_organization_service(request)
    user_orgs = (
        org_service.list_user_organizations(user_id) if auth_service.can_transfer_billing(user_id, billing) else []
    )

    pix_service = get_pix_service(request)
    pix_needs_setup = pix_service.billing_needs_setup(billing)

    return render(
        request,
        "billing/detail.html",
        {
            "billing": billing,
            "bills": bills,
            "role": role,
            "user_orgs": user_orgs,
            "pix_needs_setup": pix_needs_setup,
        },
    )


@router.get("/{billing_uuid}/edit")
async def billing_edit_form(request: Request, billing_uuid: str):
    service = get_billing_service(request)
    auth_service = get_authorization_service(request)
    billing = service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("billing_not_found", billing_uuid=billing_uuid)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)
    user_id = request.session.get("user_id")
    if not auth_service.can_edit_billing(user_id, billing):
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)
    return render(request, "billing/edit.html", {"billing": billing})


@router.post("/{billing_uuid}/edit")
async def billing_edit(request: Request, billing_uuid: str):
    service = get_billing_service(request)
    auth_service = get_authorization_service(request)
    billing = service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("billing_not_found", billing_uuid=billing_uuid)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)
    user_id = request.session.get("user_id")
    if not auth_service.can_edit_billing(user_id, billing):
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)

    previous_state = serialize_billing(billing)

    form = await request.form()
    billing.name = str(form.get("name", "")).strip()
    billing.description = str(form.get("description", "")).strip()
    billing.pix_key = str(form.get("pix_key", "")).strip()
    billing.pix_merchant_name = str(form.get("pix_merchant_name", "")).strip()
    billing.pix_merchant_city = str(form.get("pix_merchant_city", "")).strip()

    items_data = parse_formset(dict(form), "items")
    items: list[BillingItem] = []
    for row in items_data:
        desc = row.get("description", "").strip()
        if not desc:
            continue
        try:
            item_type = ItemType(row.get("item_type", "fixed"))
        except ValueError:
            item_type = ItemType.FIXED
        amount = 0
        if item_type == ItemType.FIXED:
            amount = parse_brl(row.get("amount", "")) or 0
        items.append(BillingItem(description=desc, amount=amount, item_type=item_type))

    if not items:
        logger.warning("billing_edit_rejected", billing_uuid=billing_uuid, reason="no_items")
        flash(request, "A cobrança precisa de pelo menos um item.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}/edit", status_code=302)

    billing.items = items
    try:
        updated = service.update_billing(billing)
    except ValueError as e:
        flash(request, str(e), "danger")
        return RedirectResponse(f"/billings/{billing_uuid}/edit", status_code=302)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.BILLING_UPDATE,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="billing",
        entity_id=updated.id,
        entity_uuid=updated.uuid,
        previous_state=previous_state,
        new_state=serialize_billing(updated),
    )

    flash(request, "Cobrança atualizada com sucesso!", "success")
    push_event(request, {"event": "rentivo_billing_edited", "billing_uuid_hash": analytics_hash(updated.uuid)})
    return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)


@router.post("/{billing_uuid}/transfer")
async def billing_transfer(request: Request, billing_uuid: str):
    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)
    billing = billing_service.get_billing_by_uuid(billing_uuid)
    if not billing:
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)
    user_id = request.session.get("user_id")
    if not auth_service.can_transfer_billing(user_id, billing):
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)
    form = await request.form()
    org_id_raw = str(form.get("organization_id", "")).strip()
    if not org_id_raw:
        flash(request, "Selecione uma organização.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)
    try:
        org_id = int(org_id_raw)
    except ValueError:
        flash(request, "Organização inválida.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)

    org_service = get_organization_service(request)
    if org_service.get_member(org_id, user_id) is None:
        logger.warning(
            "billing_transfer_rejected",
            billing_uuid=billing_uuid,
            org_id=org_id,
            reason="not_member",
        )
        flash(request, "Você não é membro dessa organização.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)

    previous_owner = {"owner_type": billing.owner_type, "owner_id": billing.owner_id}
    try:
        billing_service.transfer_to_organization(billing.id, org_id)
    except ValueError as e:
        flash(request, str(e), "danger")
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.BILLING_TRANSFER,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        previous_state=previous_owner,
        new_state={"owner_type": "organization", "owner_id": org_id},
    )

    flash(request, "Cobrança transferida com sucesso!", "success")
    push_event(request, {"event": "rentivo_billing_transferred", "billing_uuid_hash": analytics_hash(billing_uuid)})
    return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)


@router.post("/{billing_uuid}/delete")
async def billing_delete(request: Request, billing_uuid: str):
    service = get_billing_service(request)
    auth_service = get_authorization_service(request)
    billing = service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("billing_not_found", billing_uuid=billing_uuid)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    user_id = request.session.get("user_id")
    if not auth_service.can_delete_billing(user_id, billing):
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)

    if billing.id is None:
        logger.error("billing_missing_id", billing_uuid=billing_uuid)
        flash(request, "Cobrança inválida.", "danger")
        return RedirectResponse("/", status_code=302)
    previous_state = serialize_billing(billing)
    service.delete_billing(billing.id)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.BILLING_DELETE,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        previous_state=previous_state,
    )

    flash(request, f"Cobrança '{billing.name}' excluída.", "success")
    push_event(request, {"event": "rentivo_billing_deleted", "billing_uuid_hash": analytics_hash(billing_uuid)})
    return RedirectResponse("/", status_code=302)
