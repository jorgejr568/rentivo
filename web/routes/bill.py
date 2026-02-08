from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from landlord.models.bill import BillLineItem
from landlord.models.billing import ItemType
from web.deps import get_bill_service, get_billing_service, render
from web.flash import flash
from web.forms import parse_brl, parse_formset

router = APIRouter(prefix="/bills")


@router.get("/{billing_id}/generate")
async def bill_generate_form(request: Request, billing_id: int):
    billing_service = get_billing_service(request)
    billing = billing_service.get_billing(billing_id)
    if not billing:
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)
    return render(request, "bill/generate.html", {"billing": billing})


@router.post("/{billing_id}/generate")
async def bill_generate(request: Request, billing_id: int):
    billing_service = get_billing_service(request)
    bill_service = get_bill_service(request)

    billing = billing_service.get_billing(billing_id)
    if not billing:
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    reference_month = str(form.get("reference_month", "")).strip()
    due_date = str(form.get("due_date", "")).strip()
    notes = str(form.get("notes", "")).strip()

    if not reference_month:
        flash(request, "Mês de referência é obrigatório.", "danger")
        return RedirectResponse(f"/bills/{billing_id}/generate", status_code=302)

    # Parse variable amounts
    variable_amounts: dict[int, int] = {}
    for item in billing.items:
        if item.item_type == ItemType.VARIABLE:
            val = str(form.get(f"variable_{item.id}", ""))
            variable_amounts[item.id] = parse_brl(val) or 0  # type: ignore[index]

    # Parse extras
    extras_data = parse_formset(dict(form), "extras")
    extras: list[tuple[str, int]] = []
    for row in extras_data:
        desc = row.get("description", "").strip()
        amount = parse_brl(row.get("amount", ""))
        if desc and amount and amount > 0:
            extras.append((desc, amount))

    bill = bill_service.generate_bill(
        billing=billing,
        reference_month=reference_month,
        variable_amounts=variable_amounts,
        extras=extras,
        notes=notes,
        due_date=due_date,
    )
    flash(request, "Fatura gerada com sucesso!", "success")
    return RedirectResponse(f"/bills/{bill.id}", status_code=302)


@router.get("/{bill_id}")
async def bill_detail(request: Request, bill_id: int):
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill(bill_id)
    if not bill:
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    return render(request, "bill/detail.html", {
        "bill": bill,
        "billing": billing,
    })


@router.get("/{bill_id}/edit")
async def bill_edit_form(request: Request, bill_id: int):
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill(bill_id)
    if not bill:
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    return render(request, "bill/edit.html", {"bill": bill, "billing": billing})


@router.post("/{bill_id}/edit")
async def bill_edit(request: Request, bill_id: int):
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill(bill_id)
    if not bill:
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    due_date = str(form.get("due_date", "")).strip()
    notes = str(form.get("notes", "")).strip()

    items_data = parse_formset(dict(form), "items")
    line_items: list[BillLineItem] = []
    for i, row in enumerate(items_data):
        desc = row.get("description", "").strip()
        if not desc:
            continue
        amount = parse_brl(row.get("amount", "")) or 0
        item_type = row.get("item_type", "fixed")
        line_items.append(
            BillLineItem(
                description=desc,
                amount=amount,
                item_type=item_type,
                sort_order=i,
            )
        )

    bill = bill_service.update_bill(
        bill=bill,
        billing=billing,
        line_items=line_items,
        notes=notes,
        due_date=due_date,
    )
    flash(request, "Fatura atualizada com sucesso!", "success")
    return RedirectResponse(f"/bills/{bill.id}", status_code=302)


@router.post("/{bill_id}/regenerate-pdf")
async def bill_regenerate_pdf(request: Request, bill_id: int):
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill(bill_id)
    if not bill:
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    bill_service.regenerate_pdf(bill, billing)
    flash(request, "PDF regenerado com sucesso!", "success")
    return RedirectResponse(f"/bills/{bill.id}", status_code=302)


@router.get("/{bill_id}/invoice")
async def bill_invoice(request: Request, bill_id: int):
    bill_service = get_bill_service(request)
    bill = bill_service.get_bill(bill_id)
    if not bill or not bill.pdf_path:
        flash(request, "Fatura sem PDF.", "danger")
        return RedirectResponse("/", status_code=302)

    # Local storage: serve file directly. S3: redirect to presigned URL.
    if os.path.isfile(bill.pdf_path):
        return FileResponse(bill.pdf_path, media_type="application/pdf")

    url = bill_service.get_invoice_url(bill.pdf_path)
    return RedirectResponse(url, status_code=302)
