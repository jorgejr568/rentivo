from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse

from landlord.models.bill import BillLineItem
from landlord.models.billing import ItemType
from web.deps import get_authorization_service, get_bill_service, get_billing_service, render
from web.flash import flash
from web.forms import parse_brl, parse_formset

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billings/{billing_uuid}/bills")


@router.get("/generate")
async def bill_generate_form(request: Request, billing_uuid: str):
    logger.info("GET /bills/%s/generate — rendering form", billing_uuid)
    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)
    billing = billing_service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("Billing not found: uuid=%s", billing_uuid)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)
    user_id = request.session.get("user_id")
    if not auth_service.can_manage_bills(user_id, billing):
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)
    return render(request, "bill/generate.html", {"billing": billing})


@router.post("/generate")
async def bill_generate(request: Request, billing_uuid: str):
    logger.info("POST /bills/%s/generate — generating bill", billing_uuid)
    billing_service = get_billing_service(request)
    bill_service = get_bill_service(request)
    auth_service = get_authorization_service(request)

    billing = billing_service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("Billing not found: uuid=%s", billing_uuid)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    user_id = request.session.get("user_id")
    if not auth_service.can_manage_bills(user_id, billing):
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)

    form = await request.form()
    reference_month = str(form.get("reference_month", "")).strip()
    due_date = str(form.get("due_date", "")).strip()
    notes = str(form.get("notes", "")).strip()

    if not reference_month:
        logger.warning("Bill generate rejected: empty reference_month")
        flash(request, "Mês de referência é obrigatório.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}/bills/generate", status_code=302)

    # Parse variable amounts
    variable_amounts: dict[int, int] = {}
    for item in billing.items:
        if item.item_type == ItemType.VARIABLE:
            val = str(form.get(f"variable_{item.id}", ""))
            if item.id is not None:
                variable_amounts[item.id] = parse_brl(val) or 0

    # Parse extras
    extras_data = parse_formset(dict(form), "extras")
    extras: list[tuple[str, int]] = []
    for row in extras_data:
        desc = row.get("description", "").strip()
        amount = parse_brl(row.get("amount", ""))
        if desc and amount and amount > 0:
            extras.append((desc, amount))

    logger.info(
        "Generating bill: billing=%s month=%s due=%s variable_amounts=%s extras=%d",
        billing_uuid, reference_month, due_date, variable_amounts, len(extras),
    )

    bill = bill_service.generate_bill(
        billing=billing,
        reference_month=reference_month,
        variable_amounts=variable_amounts,
        extras=extras,
        notes=notes,
        due_date=due_date,
    )
    logger.info("Bill generated: uuid=%s total=%d", bill.uuid, bill.total_amount)
    flash(request, "Fatura gerada com sucesso!", "success")
    return RedirectResponse(f"/billings/{billing_uuid}/bills/{bill.uuid}", status_code=302)


@router.get("/{bill_uuid}")
async def bill_detail(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("GET /bills/%s — loading detail", bill_uuid)
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("Bill not found: uuid=%s", bill_uuid)
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        logger.warning("Billing not found for bill: billing_id=%s", bill.billing_id)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    user_id = request.session.get("user_id")
    if not auth_service.can_view_billing(user_id, billing):
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse("/", status_code=302)

    role = auth_service.get_role_for_billing(user_id, billing)
    logger.info("Rendering bill/detail.html for bill uuid=%s", bill_uuid)
    return render(request, "bill/detail.html", {
        "bill": bill,
        "billing": billing,
        "role": role,
    })


@router.get("/{bill_uuid}/edit")
async def bill_edit_form(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("GET /bills/%s/edit — loading edit form", bill_uuid)
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("Bill not found: uuid=%s", bill_uuid)
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        logger.warning("Billing not found for bill: billing_id=%s", bill.billing_id)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)
    return render(request, "bill/edit.html", {"bill": bill, "billing": billing})


@router.post("/{bill_uuid}/edit")
async def bill_edit(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("POST /bills/%s/edit — updating bill", bill_uuid)
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("Bill not found: uuid=%s", bill_uuid)
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        logger.warning("Billing not found for bill: billing_id=%s", bill.billing_id)
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
        try:
            item_type = ItemType(row.get("item_type", "fixed"))
        except ValueError:
            item_type = ItemType.FIXED
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

    logger.info("Updating bill uuid=%s: line_items=%d due=%s", bill_uuid, len(line_items), due_date)
    bill = bill_service.update_bill(
        bill=bill,
        billing=billing,
        line_items=line_items,
        notes=notes,
        due_date=due_date,
    )
    logger.info("Bill updated: uuid=%s total=%d", bill.uuid, bill.total_amount)
    flash(request, "Fatura atualizada com sucesso!", "success")
    return RedirectResponse(f"/billings/{billing_uuid}/bills/{bill.uuid}", status_code=302)


@router.post("/{bill_uuid}/regenerate-pdf")
async def bill_regenerate_pdf(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("POST /bills/%s/regenerate-pdf", bill_uuid)
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("Bill not found: uuid=%s", bill_uuid)
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        logger.warning("Billing not found for bill: billing_id=%s", bill.billing_id)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    bill_service.regenerate_pdf(bill, billing)
    logger.info("PDF regenerated for bill uuid=%s", bill_uuid)
    flash(request, "PDF regenerado com sucesso!", "success")
    return RedirectResponse(f"/billings/{billing_uuid}/bills/{bill.uuid}", status_code=302)


@router.post("/{bill_uuid}/toggle-paid")
async def bill_toggle_paid(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("POST /bills/%s/toggle-paid", bill_uuid)
    bill_service = get_bill_service(request)
    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("Bill not found: uuid=%s", bill_uuid)
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    bill_service.toggle_paid(bill)
    logger.info("Bill uuid=%s toggled paid: paid_at=%s", bill_uuid, bill.paid_at)
    if bill.paid_at:
        flash(request, "Fatura marcada como paga!", "success")
    else:
        flash(request, "Pagamento desmarcado.", "info")
    return RedirectResponse(f"/billings/{billing_uuid}/bills/{bill.uuid}", status_code=302)


@router.post("/{bill_uuid}/delete")
async def bill_delete(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("POST /bills/%s/delete", bill_uuid)
    bill_service = get_bill_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("Bill not found: uuid=%s", bill_uuid)
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    if bill.id is None:
        logger.error("Bill has no id: uuid=%s", bill_uuid)
        flash(request, "Fatura inválida.", "danger")
        return RedirectResponse("/", status_code=302)
    bill_service.delete_bill(bill.id)
    logger.info("Bill deleted: uuid=%s id=%s", bill_uuid, bill.id)
    flash(request, "Fatura excluída.", "success")
    return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)


@router.get("/{bill_uuid}/invoice")
async def bill_invoice(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("GET /bills/%s/invoice — serving PDF", bill_uuid)
    bill_service = get_bill_service(request)
    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill or not bill.pdf_path:
        logger.warning("Bill not found or no PDF: uuid=%s", bill_uuid)
        flash(request, "Fatura sem PDF.", "danger")
        return RedirectResponse("/", status_code=302)

    logger.info("Bill pdf_path=%s", bill.pdf_path)

    # Local storage: serve file directly. S3: redirect to presigned URL.
    if os.path.isfile(bill.pdf_path):
        logger.info("Serving local file: %s", bill.pdf_path)
        return FileResponse(bill.pdf_path, media_type="application/pdf")

    url = bill_service.get_invoice_url(bill.pdf_path)
    logger.info("Redirecting to presigned URL for bill uuid=%s", bill_uuid)
    return RedirectResponse(url, status_code=302)
