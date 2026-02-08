from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from landlord.models.billing import BillingItem, ItemType
from web.deps import get_bill_service, get_billing_service, render
from web.flash import flash
from web.forms import parse_brl, parse_formset

router = APIRouter(prefix="/billings")


@router.get("/")
async def billing_list(request: Request):
    service = get_billing_service(request)
    billings = service.list_billings()
    return render(request, "billing/list.html", {"billings": billings})


@router.get("/create")
async def billing_create_form(request: Request):
    return render(request, "billing/create.html")


@router.post("/create")
async def billing_create(request: Request):
    form = await request.form()
    name = str(form.get("name", "")).strip()
    description = str(form.get("description", "")).strip()
    pix_key = str(form.get("pix_key", "")).strip()

    if not name:
        flash(request, "Nome é obrigatório.", "danger")
        return RedirectResponse("/billings/create", status_code=302)

    items_data = parse_formset(dict(form), "items")
    items: list[BillingItem] = []
    for row in items_data:
        desc = row.get("description", "").strip()
        if not desc:
            continue
        item_type = ItemType(row.get("item_type", "fixed"))
        amount = 0
        if item_type == ItemType.FIXED:
            amount = parse_brl(row.get("amount", "")) or 0
        items.append(BillingItem(description=desc, amount=amount, item_type=item_type))

    if not items:
        flash(request, "Adicione pelo menos um item.", "danger")
        return RedirectResponse("/billings/create", status_code=302)

    service = get_billing_service(request)
    billing = service.create_billing(name, description, items, pix_key=pix_key)
    flash(request, f"Cobrança '{billing.name}' criada com sucesso!", "success")
    return RedirectResponse(f"/billings/{billing.id}", status_code=302)


@router.get("/{billing_id}")
async def billing_detail(request: Request, billing_id: int):
    billing_service = get_billing_service(request)
    bill_service = get_bill_service(request)

    billing = billing_service.get_billing(billing_id)
    if not billing:
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    bills = bill_service.list_bills(billing_id)
    return render(request, "billing/detail.html", {"billing": billing, "bills": bills})


@router.get("/{billing_id}/edit")
async def billing_edit_form(request: Request, billing_id: int):
    service = get_billing_service(request)
    billing = service.get_billing(billing_id)
    if not billing:
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)
    return render(request, "billing/edit.html", {"billing": billing})


@router.post("/{billing_id}/edit")
async def billing_edit(request: Request, billing_id: int):
    service = get_billing_service(request)
    billing = service.get_billing(billing_id)
    if not billing:
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
        item_type = ItemType(row.get("item_type", "fixed"))
        amount = 0
        if item_type == ItemType.FIXED:
            amount = parse_brl(row.get("amount", "")) or 0
        items.append(BillingItem(description=desc, amount=amount, item_type=item_type))

    if not items:
        flash(request, "A cobrança precisa de pelo menos um item.", "danger")
        return RedirectResponse(f"/billings/{billing_id}/edit", status_code=302)

    billing.items = items
    service.update_billing(billing)
    flash(request, "Cobrança atualizada com sucesso!", "success")
    return RedirectResponse(f"/billings/{billing_id}", status_code=302)


@router.post("/{billing_id}/delete")
async def billing_delete(request: Request, billing_id: int):
    service = get_billing_service(request)
    billing = service.get_billing(billing_id)
    if not billing:
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    service.delete_billing(billing_id)
    flash(request, f"Cobrança '{billing.name}' excluída.", "success")
    return RedirectResponse("/", status_code=302)
