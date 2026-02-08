from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse

from landlord.models.bill import BillLineItem
from landlord.models.billing import ItemType
from web.deps import get_bill_service, get_billing_service, render
from web.flash import flash
from web.forms import parse_brl, parse_formset

router = APIRouter(prefix="/bills")


@router.get("/{billing_uuid}/generate")
async def bill_generate_form(request: Request, billing_uuid: str):
    billing_service = get_billing_service(request)
    billing = billing_service.get_billing_by_uuid(billing_uuid)
    if not billing:
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)
    return render(request, "bill/generate.html", {"billing": billing})


@router.post("/{billing_uuid}/generate")
async def bill_generate(request: Request, billing_uuid: str):
    billing_service = get_billing_service(request)
    bill_service = get_bill_service(request)

    billing = billing_service.get_billing_by_uuid(billing_uuid)
    if not billing:
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    reference_month = str(form.get("reference_month", "")).strip()
    due_date = str(form.get("due_date", "")).strip()
    notes = str(form.get("notes", "")).strip()

    if not reference_month:
        flash(request, "Mês de referência é obrigatório.", "danger")
        return RedirectResponse(f"/bills/{billing_uuid}/generate", status_code=302)

    # Parse variable amounts
    variable_amounts: dict[int, int] = {}
    for item in billing.items:
        if item.item_type == ItemType.VARIABLE:
            val = str(form.get(f"variable_{item.id}", ""))
            assert item.id is not None
            variable_amounts[item.id] = parse_brl(val) or 0

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
    return RedirectResponse(f"/bills/{bill.uuid}", status_code=302)


@router.get("/{bill_uuid}")
async def bill_detail(request: Request, bill_uuid: str):
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    return render(request, "bill/detail.html", {
        "bill": bill,
        "billing": billing,
    })


@router.get("/{bill_uuid}/edit")
async def bill_edit_form(request: Request, bill_uuid: str):
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    return render(request, "bill/edit.html", {"bill": bill, "billing": billing})


@router.post("/{bill_uuid}/edit")
async def bill_edit(request: Request, bill_uuid: str):
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
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
        item_type = ItemType(row.get("item_type", "fixed"))
        line_items.append(
            BillLineItem(
                description=desc,
                amount=amount,
                item_type=item_type,
                sort_order=i,
            )
        )

    # Parse new extras
    extras_data = parse_formset(dict(form), "extras")
    for row in extras_data:
        desc = row.get("description", "").strip()
        amount = parse_brl(row.get("amount", ""))
        if desc and amount and amount > 0:
            line_items.append(
                BillLineItem(
                    description=desc,
                    amount=amount,
                    item_type=ItemType.EXTRA,
                    sort_order=len(line_items),
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
    return RedirectResponse(f"/bills/{bill.uuid}", status_code=302)


@router.post("/{bill_uuid}/regenerate-pdf")
async def bill_regenerate_pdf(request: Request, bill_uuid: str):
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    bill_service.regenerate_pdf(bill, billing)
    flash(request, "PDF regenerado com sucesso!", "success")
    return RedirectResponse(f"/bills/{bill.uuid}", status_code=302)


@router.post("/{bill_uuid}/toggle-paid")
async def bill_toggle_paid(request: Request, bill_uuid: str):
    bill_service = get_bill_service(request)
    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    bill_service.toggle_paid(bill)
    if bill.paid_at:
        flash(request, "Fatura marcada como paga!", "success")
    else:
        flash(request, "Pagamento desmarcado.", "info")
    return RedirectResponse(f"/bills/{bill.uuid}", status_code=302)


@router.post("/{bill_uuid}/delete")
async def bill_delete(request: Request, bill_uuid: str):
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    assert bill.id is not None
    bill_service.delete_bill(bill.id)
    flash(request, "Fatura excluída.", "success")
    if billing:
        return RedirectResponse(f"/billings/{billing.uuid}", status_code=302)
    return RedirectResponse("/", status_code=302)


@router.get("/{bill_uuid}/invoice")
async def bill_invoice(request: Request, bill_uuid: str):
    bill_service = get_bill_service(request)
    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill or not bill.pdf_path:
        flash(request, "Fatura sem PDF.", "danger")
        return RedirectResponse("/", status_code=302)

    # Local storage: serve file directly. S3: redirect to presigned URL.
    if os.path.isfile(bill.pdf_path):
        return FileResponse(bill.pdf_path, media_type="application/pdf")

    url = bill_service.get_invoice_url(bill.pdf_path)
    return RedirectResponse(url, status_code=302)
