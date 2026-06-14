from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.datastructures import UploadFile

from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import BillLineItem
from rentivo.models.billing import ItemType
from rentivo.services.audit_serializers import serialize_bill, serialize_receipt
from web.analytics import analytics_hash, push_event
from web.deps import render
from web.flash import flash, flash_redirect
from web.forms import parse_brl, parse_extras, parse_line_items, safe_redirect_path
from web.guards import BillContext, BillingContext, require_bill, require_billing
from web.receipts import attach_receipts

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/billings/{billing_uuid}/bills")


@router.get("/generate")
async def bill_generate_form(request: Request, ctx: BillingContext = Depends(require_billing("manage", pix=True))):
    return render(request, "bill/generate.html", {"billing": ctx.billing})


@router.post("/generate")
async def bill_generate(request: Request, ctx: BillingContext = Depends(require_billing("manage", pix=True))):
    billing = ctx.billing
    bill_service = request.state.services.bill

    form = await request.form()
    reference_month = str(form.get("reference_month", "")).strip()
    due_date = str(form.get("due_date", "")).strip()
    notes = str(form.get("notes", "")).strip()

    if not reference_month:
        logger.warning("bill_generate_rejected", reason="empty_reference_month")
        return flash_redirect(request, "Mês de referência é obrigatório.", f"/billings/{billing.uuid}/bills/generate")

    # Parse variable amounts
    variable_amounts: dict[int, int] = {}
    for item in billing.items:
        if item.item_type == ItemType.VARIABLE:
            val = str(form.get(f"variable_{item.id}", ""))
            if item.id is not None:
                variable_amounts[item.id] = parse_brl(val) or 0

    extras = parse_extras(dict(form))

    bill = bill_service.generate_bill(
        billing=billing,
        reference_month=reference_month,
        variable_amounts=variable_amounts,
        extras=extras,
        notes=notes,
        due_date=due_date,
        actor=request.state.actor,
    )

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.BILL_CREATE,
        entity_type="bill",
        entity_id=bill.id,
        entity_uuid=bill.uuid,
        new_state=serialize_bill(bill),
    )

    # Attach uploaded receipt files (BILL_CREATE is audited first so audit row
    # order — bill.create then receipt.upload — matches the pre-refactor flow).
    result = await attach_receipts(request, bill, billing, form.getlist("receipt_files"))
    if result.attached:
        logger.info("receipts_attached", bill_uuid=bill.uuid, count=result.attached)

    flash(request, "Fatura gerada com sucesso!", "success")
    push_event(
        request,
        {
            "event": "rentivo_bill_generated",
            "billing_uuid_hash": analytics_hash(billing.uuid),
            "bill_uuid_hash": analytics_hash(bill.uuid),
            "reference_month": bill.reference_month,
            "line_item_count": len(bill.line_items),
            "total_amount_brl": round(bill.total_amount / 100),
            "receipt_count": result.attached,
        },
    )
    return RedirectResponse(f"/billings/{billing.uuid}/bills/{bill.uuid}", status_code=302)


@router.get("/{bill_uuid}")
async def bill_detail(request: Request, ctx: BillContext = Depends(require_bill("view"))):
    bill_service = request.state.services.bill
    receipts = bill_service.list_receipts(ctx.bill.id) if ctx.bill.id else []
    communications = request.state.services.communication.list_for_bill(ctx.bill.id) if ctx.bill.id else []
    return render(
        request,
        "bill/detail.html",
        {
            "bill": ctx.bill,
            "billing": ctx.billing,
            "role": ctx.role,
            "receipts": receipts,
            "communications": communications,
        },
    )


@router.get("/{bill_uuid}/edit")
async def bill_edit_form(request: Request, ctx: BillContext = Depends(require_bill("manage"))):
    bill_service = request.state.services.bill
    receipts = bill_service.list_receipts(ctx.bill.id) if ctx.bill.id else []
    return render(request, "bill/edit.html", {"bill": ctx.bill, "billing": ctx.billing, "receipts": receipts})


@router.post("/{bill_uuid}/edit")
async def bill_edit(request: Request, ctx: BillContext = Depends(require_bill("manage", pix=True))):
    bill, billing = ctx.bill, ctx.billing
    bill_service = request.state.services.bill

    previous_state = serialize_bill(bill)

    form = await request.form()
    due_date = str(form.get("due_date", "")).strip()
    notes = str(form.get("notes", "")).strip()

    line_items: list[BillLineItem] = [
        BillLineItem(
            description=p.description,
            amount=p.amount,
            item_type=p.item_type,
            sort_order=p.index,
        )
        for p in parse_line_items(dict(form), "items")
    ]

    # Append new extras
    for description, amount in parse_extras(dict(form)):
        line_items.append(
            BillLineItem(
                description=description,
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
        actor=request.state.actor,
    )

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.BILL_UPDATE,
        entity_type="bill",
        entity_id=bill.id,
        entity_uuid=bill.uuid,
        previous_state=previous_state,
        new_state=serialize_bill(bill),
    )

    flash(request, "Fatura atualizada. O PDF será atualizado em segundo plano.", "success")
    push_event(request, {"event": "rentivo_bill_edited", "bill_uuid_hash": analytics_hash(bill.uuid)})
    return RedirectResponse(f"/billings/{billing.uuid}/bills/{bill.uuid}", status_code=302)


@router.post("/{bill_uuid}/regenerate-pdf")
async def bill_regenerate_pdf(request: Request, ctx: BillContext = Depends(require_bill("manage", pix=True))):
    bill, billing = ctx.bill, ctx.billing
    bill_service = request.state.services.bill

    old_render_status = bill.pdf_render_status
    bill_service.regenerate_pdf(bill, billing, actor=request.state.actor)

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.BILL_REGENERATE_PDF,
        entity_type="bill",
        entity_id=bill.id,
        entity_uuid=bill.uuid,
        previous_state={"pdf_render_status": old_render_status},
        new_state={"pdf_render_status": bill.pdf_render_status},
    )

    flash(
        request,
        "Regeneração do PDF iniciada. O download estará disponível em alguns segundos.",
        "success",
    )
    push_event(request, {"event": "rentivo_bill_regenerated", "bill_uuid_hash": analytics_hash(bill.uuid)})
    return RedirectResponse(f"/billings/{billing.uuid}/bills/{bill.uuid}", status_code=302)


@router.post("/{bill_uuid}/change-status")
async def bill_change_status(request: Request, ctx: BillContext = Depends(require_bill("manage"))):
    bill, billing = ctx.bill, ctx.billing
    bill_service = request.state.services.bill

    form = await request.form()
    new_status = str(form.get("status", "")).strip()
    previous_status = bill.status

    try:
        bill_service.change_status(bill, new_status)
    except ValueError:
        return flash_redirect(request, "Status inválido.", f"/billings/{billing.uuid}/bills/{bill.uuid}")

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.BILL_STATUS_CHANGE,
        entity_type="bill",
        entity_id=bill.id,
        entity_uuid=bill.uuid,
        previous_state={"status": previous_status},
        new_state={"status": bill.status},
    )

    flash(request, "Status atualizado!", "success")
    push_event(
        request,
        {
            "event": "rentivo_bill_status_changed",
            "bill_uuid_hash": analytics_hash(bill.uuid),
            "new_status": new_status,
        },
    )
    return RedirectResponse(f"/billings/{billing.uuid}/bills/{bill.uuid}", status_code=302)


@router.post("/{bill_uuid}/delete")
async def bill_delete(request: Request, ctx: BillContext = Depends(require_bill("delete"))):
    bill, billing = ctx.bill, ctx.billing
    bill_service = request.state.services.bill

    if bill.id is None:
        logger.error("bill_missing_id", bill_uuid=bill.uuid)
        return flash_redirect(request, "Fatura inválida.", "/")
    previous_state = serialize_bill(bill)

    cleanup = request.state.services.storage_cleanup
    cleanup.enqueue_bill_delete_cascade(request.state.actor, bill)

    bill_service.delete_bill(bill.id)

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.BILL_DELETE,
        entity_type="bill",
        entity_id=bill.id,
        entity_uuid=bill.uuid,
        previous_state=previous_state,
    )

    flash(request, "Fatura excluída.", "success")
    push_event(request, {"event": "rentivo_bill_deleted", "bill_uuid_hash": analytics_hash(bill.uuid)})
    return RedirectResponse(f"/billings/{billing.uuid}", status_code=302)


@router.get("/{bill_uuid}/invoice")
async def bill_invoice(request: Request, ctx: BillContext = Depends(require_bill("view"))):
    bill = ctx.bill

    if not bill.pdf_path:
        logger.warning("bill_no_pdf", bill_uuid=bill.uuid)
        return flash_redirect(request, "Fatura sem PDF.", "/")

    ref = request.state.services.bill.get_invoice_ref(bill)
    logger.debug("bill_pdf_ref", storage_key=bill.pdf_path, kind=ref.kind)
    if ref.kind == "local":
        return FileResponse(ref.location, media_type="application/pdf")
    return RedirectResponse(ref.location, status_code=302)


@router.get("/{bill_uuid}/receipts/{receipt_uuid}")
async def receipt_view(request: Request, receipt_uuid: str, ctx: BillContext = Depends(require_bill("view"))):
    bill_service = request.state.services.bill

    receipt = bill_service.get_receipt_by_uuid(receipt_uuid)
    if not receipt or not receipt.storage_key or receipt.bill_id != ctx.bill.id:
        return flash_redirect(request, "Comprovante não encontrado.", "/")

    ref = bill_service.get_receipt_ref(receipt)
    if ref.kind == "local":
        return FileResponse(ref.location, media_type=receipt.content_type)
    return RedirectResponse(ref.location, status_code=302)


@router.post("/{bill_uuid}/receipts/upload")
async def receipt_upload(request: Request, ctx: BillContext = Depends(require_bill("manage", pix=True))):
    bill, billing = ctx.bill, ctx.billing

    form = await request.form()
    redirect_url = safe_redirect_path(
        str(form.get("next", "")),
        f"/billings/{billing.uuid}/bills/{bill.uuid}/edit",
    )

    uploads = [u for u in form.getlist("receipt_files") if isinstance(u, UploadFile) and u.filename]
    if not uploads:
        logger.warning("receipt_upload_no_file", bill_uuid=bill.uuid)
        return flash_redirect(request, "Nenhum arquivo selecionado.", redirect_url)

    result = await attach_receipts(request, bill, billing, uploads)

    if result.attached == 1:
        flash(request, "Comprovante anexado. O PDF será atualizado em segundo plano.", "success")
    elif result.attached > 1:
        flash(
            request,
            f"{result.attached} comprovantes anexados. O PDF será atualizado em segundo plano.",
            "success",
        )
    if result.attached > 0:
        push_event(
            request,
            {
                "event": "rentivo_receipt_uploaded",
                "bill_uuid_hash": analytics_hash(bill.uuid),
                "count": result.attached,
                "total_bytes": result.total_bytes,
            },
        )
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/{bill_uuid}/receipts/{receipt_uuid}/delete")
async def receipt_delete(request: Request, receipt_uuid: str, ctx: BillContext = Depends(require_bill("manage"))):
    bill, billing = ctx.bill, ctx.billing
    bill_service = request.state.services.bill

    form = await request.form()
    redirect_url = safe_redirect_path(
        str(form.get("next", "")),
        f"/billings/{billing.uuid}/bills/{bill.uuid}/edit",
    )

    receipt = bill_service.get_receipt_by_uuid(receipt_uuid)
    if not receipt or receipt.bill_id != bill.id:
        logger.warning("receipt_not_found", receipt_uuid=receipt_uuid)
        return flash_redirect(request, "Comprovante não encontrado.", redirect_url)

    previous_state = serialize_receipt(receipt, bill_uuid=bill.uuid, billing_uuid=billing.uuid)
    bill_service.delete_receipt(receipt, bill, billing, actor=request.state.actor)

    cleanup = request.state.services.storage_cleanup
    cleanup.enqueue_receipt_delete(request.state.actor, receipt)

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.RECEIPT_DELETE,
        entity_type="receipt",
        entity_id=receipt.id,
        entity_uuid=receipt_uuid,
        previous_state=previous_state,
    )

    flash(request, "Comprovante removido. O PDF será atualizado em segundo plano.", "success")
    push_event(request, {"event": "rentivo_receipt_deleted", "bill_uuid_hash": analytics_hash(bill.uuid)})
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/{bill_uuid}/receipts/reorder")
async def receipt_reorder(request: Request, ctx: BillContext = Depends(require_bill("manage", json=True))):
    bill, billing = ctx.bill, ctx.billing
    bill_service = request.state.services.bill

    try:
        body = await request.json()
        receipt_uuids = body.get("order", [])
    except Exception:
        return JSONResponse({"error": "JSON inválido."}, status_code=400)

    if not isinstance(receipt_uuids, list):
        return JSONResponse({"error": "Campo 'order' deve ser uma lista."}, status_code=400)

    try:
        bill_service.reorder_receipts(bill, billing, receipt_uuids, actor=request.state.actor)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.RECEIPT_REORDER,
        entity_type="bill",
        entity_id=bill.id,
        entity_uuid=bill.uuid,
        new_state={"order": receipt_uuids},
    )

    return JSONResponse({"ok": True})
