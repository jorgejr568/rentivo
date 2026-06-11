from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from rentivo.models.audit_log import AuditEventType
from rentivo.models.billing import BillingItem
from rentivo.services.audit_serializers import serialize_billing
from web.analytics import analytics_hash, push_event
from web.deps import render
from web.flash import flash
from web.forms import parse_line_items
from web.guards import BillingContext, require_billing

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/billings")


@router.get("/")
async def billing_list(request: Request):
    service = request.state.services.billing
    pix_service = request.state.services.pix
    user_id = request.session.get("user_id")
    billings = service.list_billings_for_user(user_id)
    billings_needing_pix = [b for b in billings if pix_service.billing_needs_setup(b)]
    user_pix_incomplete = pix_service.owner_needs_setup("user", user_id) if user_id else False
    stats = request.state.services.billing_stats.stats_for_ids([b.id for b in billings])
    return render(
        request,
        "billing/list.html",
        {
            "billings": billings,
            "billings_needing_pix": billings_needing_pix,
            "user_pix_incomplete": user_pix_incomplete,
            "stats": stats,
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

    items: list[BillingItem] = [
        BillingItem(description=p.description, amount=p.amount, item_type=p.item_type)
        for p in parse_line_items(dict(form), "items", amount_only_for_fixed=True)
    ]

    if not items:
        logger.warning("billing_create_rejected", reason="no_items")
        flash(request, "Adicione pelo menos um item.", "danger")
        return RedirectResponse("/billings/create", status_code=302)

    service = request.state.services.billing
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

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.BILLING_CREATE,
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
async def billing_detail(request: Request, ctx: BillingContext = Depends(require_billing("view"))):
    billing = ctx.billing
    bill_service = request.state.services.bill
    auth_service = request.state.services.authorization

    if billing.id is None:
        logger.error("billing_missing_id", billing_uuid=billing.uuid)
        flash(request, "Cobrança inválida.", "danger")
        return RedirectResponse("/", status_code=302)

    bills = bill_service.list_bills(billing.id)

    # Load user's orgs for transfer dropdown
    org_service = request.state.services.organization
    user_orgs = (
        org_service.list_user_organizations(ctx.user_id)
        if auth_service.can_transfer_billing(ctx.user_id, billing)
        else []
    )

    pix_service = request.state.services.pix
    pix_needs_setup = pix_service.billing_needs_setup(billing)

    return render(
        request,
        "billing/detail.html",
        {
            "billing": billing,
            "bills": bills,
            "role": ctx.role,
            "user_orgs": user_orgs,
            "pix_needs_setup": pix_needs_setup,
        },
    )


@router.get("/{billing_uuid}/edit")
async def billing_edit_form(request: Request, ctx: BillingContext = Depends(require_billing("edit"))):
    return render(request, "billing/edit.html", {"billing": ctx.billing})


@router.post("/{billing_uuid}/edit")
async def billing_edit(request: Request, ctx: BillingContext = Depends(require_billing("edit"))):
    billing = ctx.billing
    service = request.state.services.billing

    previous_state = serialize_billing(billing)

    form = await request.form()
    billing.name = str(form.get("name", "")).strip()
    billing.description = str(form.get("description", "")).strip()
    billing.pix_key = str(form.get("pix_key", "")).strip()
    billing.pix_merchant_name = str(form.get("pix_merchant_name", "")).strip()
    billing.pix_merchant_city = str(form.get("pix_merchant_city", "")).strip()

    items: list[BillingItem] = [
        BillingItem(description=p.description, amount=p.amount, item_type=p.item_type)
        for p in parse_line_items(dict(form), "items", amount_only_for_fixed=True)
    ]

    if not items:
        logger.warning("billing_edit_rejected", billing_uuid=billing.uuid, reason="no_items")
        flash(request, "A cobrança precisa de pelo menos um item.", "danger")
        return RedirectResponse(f"/billings/{billing.uuid}/edit", status_code=302)

    billing.items = items
    try:
        updated = service.update_billing(billing)
    except ValueError as e:
        flash(request, str(e), "danger")
        return RedirectResponse(f"/billings/{billing.uuid}/edit", status_code=302)

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.BILLING_UPDATE,
        entity_type="billing",
        entity_id=updated.id,
        entity_uuid=updated.uuid,
        previous_state=previous_state,
        new_state=serialize_billing(updated),
    )

    flash(request, "Cobrança atualizada com sucesso!", "success")
    push_event(request, {"event": "rentivo_billing_edited", "billing_uuid_hash": analytics_hash(updated.uuid)})
    return RedirectResponse(f"/billings/{billing.uuid}", status_code=302)


@router.post("/{billing_uuid}/transfer")
async def billing_transfer(request: Request, ctx: BillingContext = Depends(require_billing("transfer"))):
    billing = ctx.billing
    billing_service = request.state.services.billing

    form = await request.form()
    org_id_raw = str(form.get("organization_id", "")).strip()
    if not org_id_raw:
        flash(request, "Selecione uma organização.", "danger")
        return RedirectResponse(f"/billings/{billing.uuid}", status_code=302)
    try:
        org_id = int(org_id_raw)
    except ValueError:
        flash(request, "Organização inválida.", "danger")
        return RedirectResponse(f"/billings/{billing.uuid}", status_code=302)

    org_service = request.state.services.organization
    if org_service.get_member(org_id, ctx.user_id) is None:
        logger.warning(
            "billing_transfer_rejected",
            billing_uuid=billing.uuid,
            org_id=org_id,
            reason="not_member",
        )
        flash(request, "Você não é membro dessa organização.", "danger")
        return RedirectResponse(f"/billings/{billing.uuid}", status_code=302)

    previous_owner = {"owner_type": billing.owner_type, "owner_id": billing.owner_id}
    try:
        billing_service.transfer_to_organization(billing.id, org_id)
    except ValueError as e:
        flash(request, str(e), "danger")
        return RedirectResponse(f"/billings/{billing.uuid}", status_code=302)

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.BILLING_TRANSFER,
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        previous_state=previous_owner,
        new_state={"owner_type": "organization", "owner_id": org_id},
    )

    request.state.services.billing_notification.notify_transferred(
        billing=billing,
        previous_owner=previous_owner,
        new_org_id=org_id,
        actor_user_id=ctx.user_id,
        actor_email=request.session.get("email", ""),
    )

    flash(request, "Cobrança transferida com sucesso!", "success")
    push_event(request, {"event": "rentivo_billing_transferred", "billing_uuid_hash": analytics_hash(billing.uuid)})
    return RedirectResponse(f"/billings/{billing.uuid}", status_code=302)


@router.post("/{billing_uuid}/delete")
async def billing_delete(request: Request, ctx: BillingContext = Depends(require_billing("delete"))):
    billing = ctx.billing
    service = request.state.services.billing

    if billing.id is None:
        logger.error("billing_missing_id", billing_uuid=billing.uuid)
        flash(request, "Cobrança inválida.", "danger")
        return RedirectResponse("/", status_code=302)
    previous_state = serialize_billing(billing)

    cleanup = request.state.services.storage_cleanup
    cleanup.enqueue_billing_delete_cascade(
        billing,
        source="web",
        actor_id=ctx.user_id,
        actor_username=request.session.get("email", ""),
    )

    service.delete_billing(billing.id)

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.BILLING_DELETE,
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        previous_state=previous_state,
    )

    flash(request, f"Cobrança '{billing.name}' excluída.", "success")
    push_event(request, {"event": "rentivo_billing_deleted", "billing_uuid_hash": analytics_hash(billing.uuid)})
    return RedirectResponse("/", status_code=302)
