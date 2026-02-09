from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from landlord.models.billing import BillingItem, ItemType
from web.deps import get_bill_service, get_billing_service, render
from web.flash import flash
from web.forms import parse_brl, parse_formset

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billings")


@router.get("/")
async def billing_list(request: Request):
    logger.info("GET /billings/ — listing billings")
    service = get_billing_service(request)
    billings = service.list_billings()
    logger.info("Found %d billings", len(billings))
    return render(request, "billing/list.html", {"billings": billings})


@router.get("/create")
async def billing_create_form(request: Request):
    logger.info("GET /billings/create — rendering form")
    return render(request, "billing/create.html")


@router.post("/create")
async def billing_create(request: Request):
    logger.info("POST /billings/create — creating billing")
    form = await request.form()
    name = str(form.get("name", "")).strip()
    description = str(form.get("description", "")).strip()
    pix_key = str(form.get("pix_key", "")).strip()

    if not name:
        logger.warning("Billing create rejected: empty name")
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
        logger.warning("Billing create rejected: no items")
        flash(request, "Adicione pelo menos um item.", "danger")
        return RedirectResponse("/billings/create", status_code=302)

    service = get_billing_service(request)
    billing = service.create_billing(name, description, items, pix_key=pix_key)
    logger.info("Billing created: uuid=%s name=%s items=%d", billing.uuid, billing.name, len(items))
    flash(request, f"Cobrança '{billing.name}' criada com sucesso!", "success")
    return RedirectResponse(f"/billings/{billing.uuid}", status_code=302)


@router.get("/{billing_uuid}")
async def billing_detail(request: Request, billing_uuid: str):
    logger.info("GET /billings/%s — loading detail", billing_uuid)
    billing_service = get_billing_service(request)
    bill_service = get_bill_service(request)

    billing = billing_service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("Billing not found: uuid=%s", billing_uuid)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    logger.info("Billing loaded: id=%s name=%s items=%d", billing.id, billing.name, len(billing.items))

    if billing.id is None:
        logger.error("Billing has no id: uuid=%s", billing_uuid)
        flash(request, "Cobrança inválida.", "danger")
        return RedirectResponse("/", status_code=302)

    bills = bill_service.list_bills(billing.id)
    logger.info("Found %d bills for billing id=%s", len(bills), billing.id)
    for bill in bills:
        logger.info(
            "  bill uuid=%s month=%s total=%d due=%s paid_at=%s status=%s",
            bill.uuid, bill.reference_month, bill.total_amount,
            bill.due_date, bill.paid_at, bill.payment_status,
        )
    logger.info("Rendering billing/detail.html")
    return render(request, "billing/detail.html", {"billing": billing, "bills": bills})


@router.get("/{billing_uuid}/edit")
async def billing_edit_form(request: Request, billing_uuid: str):
    logger.info("GET /billings/%s/edit — loading edit form", billing_uuid)
    service = get_billing_service(request)
    billing = service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("Billing not found: uuid=%s", billing_uuid)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)
    return render(request, "billing/edit.html", {"billing": billing})


@router.post("/{billing_uuid}/edit")
async def billing_edit(request: Request, billing_uuid: str):
    logger.info("POST /billings/%s/edit — updating billing", billing_uuid)
    service = get_billing_service(request)
    billing = service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("Billing not found: uuid=%s", billing_uuid)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    billing.name = str(form.get("name", "")).strip()
    billing.description = str(form.get("description", "")).strip()
    billing.pix_key = str(form.get("pix_key", "")).strip()

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
        logger.warning("Billing edit rejected: no items for uuid=%s", billing_uuid)
        flash(request, "A cobrança precisa de pelo menos um item.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}/edit", status_code=302)

    billing.items = items
    service.update_billing(billing)
    logger.info("Billing updated: uuid=%s name=%s items=%d", billing_uuid, billing.name, len(items))
    flash(request, "Cobrança atualizada com sucesso!", "success")
    return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)


@router.post("/{billing_uuid}/delete")
async def billing_delete(request: Request, billing_uuid: str):
    logger.info("POST /billings/%s/delete — deleting billing", billing_uuid)
    service = get_billing_service(request)
    billing = service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("Billing not found: uuid=%s", billing_uuid)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    if billing.id is None:
        logger.error("Billing has no id: uuid=%s", billing_uuid)
        flash(request, "Cobrança inválida.", "danger")
        return RedirectResponse("/", status_code=302)
    service.delete_billing(billing.id)
    logger.info("Billing deleted: uuid=%s name=%s", billing_uuid, billing.name)
    flash(request, f"Cobrança '{billing.name}' excluída.", "success")
    return RedirectResponse("/", status_code=302)
