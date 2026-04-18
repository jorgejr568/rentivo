from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.datastructures import UploadFile

from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import BillLineItem
from rentivo.models.billing import ItemType
from rentivo.models.receipt import ALLOWED_RECEIPT_TYPES, MAX_RECEIPT_SIZE
from rentivo.services.audit_serializers import serialize_bill
from web.deps import get_audit_service, get_authorization_service, get_bill_service, get_billing_service, render
from web.flash import flash
from web.forms import parse_brl, parse_formset

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billings/{billing_uuid}/bills")


def _danger_redirect(request: Request, message: str, location: str) -> RedirectResponse:
    flash(request, message, "danger")
    return RedirectResponse(location, status_code=302)


def _safe_redirect_target(target: str, default: str) -> str:
    if target.startswith("/") and not target.startswith("//"):
        return target
    return default


def _load_bill_context(
    request: Request,
    billing_uuid: str,
    bill_uuid: str,
    *,
    require_manage: bool,
    denied_redirect: str,
):
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("Bill not found: uuid=%s", bill_uuid)
        return _danger_redirect(request, "Fatura não encontrada.", "/")

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        logger.warning("Billing not found for bill: billing_id=%s", bill.billing_id)
        return _danger_redirect(request, "Cobrança não encontrada.", "/")
    if billing.uuid != billing_uuid:
        logger.warning(
            "Bill path mismatch: bill_uuid=%s actual_billing_uuid=%s requested_billing_uuid=%s",
            bill_uuid,
            billing.uuid,
            billing_uuid,
        )
        return _danger_redirect(request, "Fatura não encontrada.", "/")

    user_id = request.session.get("user_id")
    if require_manage:
        allowed = auth_service.can_manage_bills(user_id, billing)
    else:
        allowed = auth_service.can_view_billing(user_id, billing)
    if not allowed:
        logger.warning(
            "Bill access denied: billing=%s bill=%s user=%s require_manage=%s",
            billing_uuid,
            bill_uuid,
            user_id,
            require_manage,
        )
        return _danger_redirect(request, "Acesso negado.", denied_redirect)

    return bill_service, auth_service, bill, billing, user_id


def _load_receipt_for_bill(
    request: Request,
    bill_service,
    bill,
    receipt_uuid: str,
    *,
    redirect_url: str,
):
    receipt = bill_service.get_receipt_by_uuid(receipt_uuid)
    if not receipt or bill.id is None or receipt.bill_id != bill.id:
        logger.warning(
            "Receipt not found for bill: bill_uuid=%s receipt_uuid=%s bill_id=%s",
            bill.uuid,
            receipt_uuid,
            bill.id,
        )
        return _danger_redirect(request, "Comprovante não encontrado.", redirect_url)
    return receipt


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
        billing_uuid,
        reference_month,
        due_date,
        variable_amounts,
        len(extras),
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

    # Attach uploaded receipt files
    receipt_files = form.getlist("receipt_files")
    attached_receipts = []
    for upload in receipt_files:
        if not isinstance(upload, UploadFile) or not upload.filename:
            continue
        file_bytes = await upload.read()
        content_type = upload.content_type or ""
        if not file_bytes or content_type not in ALLOWED_RECEIPT_TYPES:
            continue
        if len(file_bytes) > MAX_RECEIPT_SIZE:
            continue
        receipt = bill_service.add_receipt(
            bill=bill,
            billing=billing,
            filename=upload.filename,
            file_bytes=file_bytes,
            content_type=content_type,
        )
        attached_receipts.append(receipt)
    if attached_receipts:
        logger.info("Attached %d receipts to bill uuid=%s", len(attached_receipts), bill.uuid)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.BILL_CREATE,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="bill",
        entity_id=bill.id,
        entity_uuid=bill.uuid,
        new_state=serialize_bill(bill),
    )
    for receipt in attached_receipts:
        audit.safe_log(
            AuditEventType.RECEIPT_UPLOAD,
            actor_id=user_id,
            actor_username=request.session.get("username", ""),
            source="web",
            entity_type="receipt",
            entity_id=receipt.id,
            entity_uuid=receipt.uuid,
            new_state={
                "filename": receipt.filename,
                "content_type": receipt.content_type,
                "file_size": receipt.file_size,
                "bill_uuid": bill.uuid,
                "billing_uuid": billing_uuid,
            },
        )

    flash(request, "Fatura gerada com sucesso!", "success")
    return RedirectResponse(f"/billings/{billing_uuid}/bills/{bill.uuid}", status_code=302)


@router.get("/{bill_uuid}")
async def bill_detail(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("GET /bills/%s — loading detail", bill_uuid)
    context = _load_bill_context(
        request,
        billing_uuid,
        bill_uuid,
        require_manage=False,
        denied_redirect="/",
    )
    if isinstance(context, RedirectResponse):
        return context

    bill_service, auth_service, bill, billing, user_id = context
    role = auth_service.get_role_for_billing(user_id, billing)
    receipts = bill_service.list_receipts(bill.id) if bill.id else []
    logger.info("Rendering bill/detail.html for bill uuid=%s", bill_uuid)
    return render(
        request,
        "bill/detail.html",
        {
            "bill": bill,
            "billing": billing,
            "role": role,
            "receipts": receipts,
        },
    )


@router.get("/{bill_uuid}/edit")
async def bill_edit_form(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("GET /bills/%s/edit — loading edit form", bill_uuid)
    context = _load_bill_context(
        request,
        billing_uuid,
        bill_uuid,
        require_manage=True,
        denied_redirect=f"/billings/{billing_uuid}/bills/{bill_uuid}",
    )
    if isinstance(context, RedirectResponse):
        return context

    bill_service, _, bill, billing, _ = context
    receipts = bill_service.list_receipts(bill.id) if bill.id else []
    return render(request, "bill/edit.html", {"bill": bill, "billing": billing, "receipts": receipts})


@router.post("/{bill_uuid}/edit")
async def bill_edit(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("POST /bills/%s/edit — updating bill", bill_uuid)
    context = _load_bill_context(
        request,
        billing_uuid,
        bill_uuid,
        require_manage=True,
        denied_redirect=f"/billings/{billing_uuid}/bills/{bill_uuid}",
    )
    if isinstance(context, RedirectResponse):
        return context

    bill_service, _, bill, billing, user_id = context
    previous_state = serialize_bill(bill)

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

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.BILL_UPDATE,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="bill",
        entity_id=bill.id,
        entity_uuid=bill.uuid,
        previous_state=previous_state,
        new_state=serialize_bill(bill),
    )

    flash(request, "Fatura atualizada com sucesso!", "success")
    return RedirectResponse(f"/billings/{billing_uuid}/bills/{bill.uuid}", status_code=302)


@router.post("/{bill_uuid}/regenerate-pdf")
async def bill_regenerate_pdf(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("POST /bills/%s/regenerate-pdf", bill_uuid)
    context = _load_bill_context(
        request,
        billing_uuid,
        bill_uuid,
        require_manage=True,
        denied_redirect=f"/billings/{billing_uuid}/bills/{bill_uuid}",
    )
    if isinstance(context, RedirectResponse):
        return context

    bill_service, _, bill, billing, user_id = context
    old_pdf_path = bill.pdf_path
    bill_service.regenerate_pdf(bill, billing)
    logger.info("PDF regenerated for bill uuid=%s", bill_uuid)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.BILL_REGENERATE_PDF,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="bill",
        entity_id=bill.id,
        entity_uuid=bill.uuid,
        previous_state={"pdf_path": old_pdf_path},
        new_state={"pdf_path": bill.pdf_path},
    )

    flash(request, "PDF regenerado com sucesso!", "success")
    return RedirectResponse(f"/billings/{billing_uuid}/bills/{bill.uuid}", status_code=302)


@router.post("/{bill_uuid}/change-status")
async def bill_change_status(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("POST /bills/%s/change-status", bill_uuid)
    context = _load_bill_context(
        request,
        billing_uuid,
        bill_uuid,
        require_manage=True,
        denied_redirect=f"/billings/{billing_uuid}",
    )
    if isinstance(context, RedirectResponse):
        return context

    bill_service, _, bill, billing, user_id = context

    form = await request.form()
    new_status = str(form.get("status", "")).strip()
    previous_status = bill.status

    try:
        bill_service.change_status(bill, new_status)
    except ValueError:
        flash(request, "Status inválido.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}/bills/{bill_uuid}", status_code=302)

    logger.info("Bill uuid=%s status changed: %s -> %s", bill_uuid, previous_status, new_status)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.BILL_STATUS_CHANGE,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="bill",
        entity_id=bill.id,
        entity_uuid=bill.uuid,
        previous_state={"status": previous_status},
        new_state={"status": bill.status},
    )

    flash(request, "Status atualizado!", "success")
    return RedirectResponse(f"/billings/{billing_uuid}/bills/{bill.uuid}", status_code=302)


@router.post("/{bill_uuid}/delete")
async def bill_delete(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("POST /bills/%s/delete", bill_uuid)
    context = _load_bill_context(
        request,
        billing_uuid,
        bill_uuid,
        require_manage=True,
        denied_redirect=f"/billings/{billing_uuid}/bills/{bill_uuid}",
    )
    if isinstance(context, RedirectResponse):
        return context

    bill_service, _, bill, _, user_id = context
    if bill.id is None:
        logger.error("Bill has no id: uuid=%s", bill_uuid)
        flash(request, "Fatura inválida.", "danger")
        return RedirectResponse("/", status_code=302)
    previous_state = serialize_bill(bill)
    bill_service.delete_bill(bill.id)
    logger.info("Bill deleted: uuid=%s id=%s", bill_uuid, bill.id)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.BILL_DELETE,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="bill",
        entity_id=bill.id,
        entity_uuid=bill.uuid,
        previous_state=previous_state,
    )

    flash(request, "Fatura excluída.", "success")
    return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)


@router.get("/{bill_uuid}/invoice")
async def bill_invoice(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("GET /bills/%s/invoice — serving PDF", bill_uuid)
    context = _load_bill_context(
        request,
        billing_uuid,
        bill_uuid,
        require_manage=False,
        denied_redirect="/",
    )
    if isinstance(context, RedirectResponse):
        return context

    bill_service, _, bill, _, _ = context
    if not bill.pdf_path:
        logger.warning("Bill has no PDF: uuid=%s", bill_uuid)
        return _danger_redirect(request, "Fatura sem PDF.", "/")
    logger.info("Bill pdf_path=%s", bill.pdf_path)

    # Local storage: serve file directly. S3: redirect to presigned URL.
    if os.path.isfile(bill.pdf_path):
        logger.info("Serving local file: %s", bill.pdf_path)
        return FileResponse(bill.pdf_path, media_type="application/pdf")

    url = bill_service.get_invoice_url(bill.pdf_path)
    logger.info("Redirecting to presigned URL for bill uuid=%s", bill_uuid)
    return RedirectResponse(url, status_code=302)


@router.get("/{bill_uuid}/receipts/{receipt_uuid}")
async def receipt_view(request: Request, billing_uuid: str, bill_uuid: str, receipt_uuid: str):
    logger.info("GET /bills/%s/receipts/%s — serving file", bill_uuid, receipt_uuid)
    context = _load_bill_context(
        request,
        billing_uuid,
        bill_uuid,
        require_manage=False,
        denied_redirect="/",
    )
    if isinstance(context, RedirectResponse):
        return context

    bill_service, _, bill, _, _ = context
    receipt = _load_receipt_for_bill(
        request,
        bill_service,
        bill,
        receipt_uuid,
        redirect_url="/",
    )
    if isinstance(receipt, RedirectResponse):
        return receipt
    if not receipt.storage_key:
        return _danger_redirect(request, "Comprovante não encontrado.", "/")

    url_or_path = bill_service.storage.get_url(receipt.storage_key)

    if os.path.isfile(url_or_path):
        return FileResponse(url_or_path, media_type=receipt.content_type)

    return RedirectResponse(url_or_path, status_code=302)


@router.post("/{bill_uuid}/receipts/upload")
async def receipt_upload(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("POST /bills/%s/receipts/upload", bill_uuid)
    form = await request.form()
    default_redirect = f"/billings/{billing_uuid}/bills/{bill_uuid}/edit"
    redirect_url = _safe_redirect_target(str(form.get("next", "")).strip(), default_redirect) or default_redirect
    context = _load_bill_context(
        request,
        billing_uuid,
        bill_uuid,
        require_manage=True,
        denied_redirect=redirect_url,
    )
    if isinstance(context, RedirectResponse):
        return context

    bill_service, _, bill, billing, _ = context
    uploads = form.getlist("receipt_files")
    valid_uploads = [u for u in uploads if isinstance(u, UploadFile) and u.filename]
    if not valid_uploads:
        logger.warning("No file uploaded for bill uuid=%s", bill_uuid)
        flash(request, "Nenhum arquivo selecionado.", "danger")
        return RedirectResponse(redirect_url, status_code=302)

    attached = 0
    skipped = 0
    audit = get_audit_service(request)
    for upload in valid_uploads:
        file_bytes = await upload.read()
        content_type = upload.content_type or ""

        if content_type not in ALLOWED_RECEIPT_TYPES:
            logger.warning("Invalid file type: %s", content_type)
            skipped += 1
            continue
        if not file_bytes:
            skipped += 1
            continue
        if len(file_bytes) > MAX_RECEIPT_SIZE:
            skipped += 1
            continue

        receipt = bill_service.add_receipt(
            bill=bill,
            billing=billing,
            filename=upload.filename,
            file_bytes=file_bytes,
            content_type=content_type,
        )
        logger.info("Receipt uploaded for bill uuid=%s", bill_uuid)
        attached += 1

        audit.safe_log(
            AuditEventType.RECEIPT_UPLOAD,
            actor_id=request.session.get("user_id"),
            actor_username=request.session.get("username", ""),
            source="web",
            entity_type="receipt",
            entity_id=receipt.id,
            entity_uuid=receipt.uuid,
            new_state={
                "filename": receipt.filename,
                "content_type": receipt.content_type,
                "file_size": receipt.file_size,
                "bill_uuid": bill_uuid,
                "billing_uuid": billing_uuid,
            },
        )

    if attached == 1:
        flash(request, "Comprovante anexado com sucesso!", "success")
    elif attached > 1:
        flash(request, f"{attached} comprovantes anexados com sucesso!", "success")
    if skipped:
        flash(request, f"{skipped} arquivo(s) ignorado(s) (tipo inválido, vazio ou muito grande).", "warning")
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/{bill_uuid}/receipts/{receipt_uuid}/delete")
async def receipt_delete(request: Request, billing_uuid: str, bill_uuid: str, receipt_uuid: str):
    logger.info("POST /bills/%s/receipts/%s/delete", bill_uuid, receipt_uuid)
    form = await request.form()
    default_redirect = f"/billings/{billing_uuid}/bills/{bill_uuid}/edit"
    redirect_url = _safe_redirect_target(str(form.get("next", "")).strip(), default_redirect) or default_redirect
    context = _load_bill_context(
        request,
        billing_uuid,
        bill_uuid,
        require_manage=True,
        denied_redirect=redirect_url,
    )
    if isinstance(context, RedirectResponse):
        return context

    bill_service, _, bill, billing, _ = context
    receipt = _load_receipt_for_bill(
        request,
        bill_service,
        bill,
        receipt_uuid,
        redirect_url=redirect_url,
    )
    if isinstance(receipt, RedirectResponse):
        return receipt

    previous_state = {
        "filename": receipt.filename,
        "content_type": receipt.content_type,
        "file_size": receipt.file_size,
        "bill_uuid": bill_uuid,
        "billing_uuid": billing_uuid,
    }
    bill_service.delete_receipt(receipt, bill, billing)
    logger.info("Receipt deleted: uuid=%s", receipt_uuid)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.RECEIPT_DELETE,
        actor_id=request.session.get("user_id"),
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="receipt",
        entity_id=receipt.id,
        entity_uuid=receipt_uuid,
        previous_state=previous_state,
    )

    flash(request, "Comprovante removido.", "success")
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/{bill_uuid}/receipts/reorder")
async def receipt_reorder(request: Request, billing_uuid: str, bill_uuid: str):
    logger.info("POST /bills/%s/receipts/reorder", bill_uuid)
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        return JSONResponse({"error": "Fatura não encontrada."}, status_code=404)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        return JSONResponse({"error": "Cobrança não encontrada."}, status_code=404)
    if billing.uuid != billing_uuid:
        logger.warning(
            "Receipt reorder path mismatch: bill_uuid=%s actual_billing_uuid=%s requested_billing_uuid=%s",
            bill_uuid,
            billing.uuid,
            billing_uuid,
        )
        return JSONResponse({"error": "Fatura não encontrada."}, status_code=404)

    user_id = request.session.get("user_id")
    if not auth_service.can_manage_bills(user_id, billing):
        return JSONResponse({"error": "Acesso negado."}, status_code=403)

    try:
        body = await request.json()
        receipt_uuids = body.get("order", [])
    except Exception:
        return JSONResponse({"error": "JSON inválido."}, status_code=400)

    if not isinstance(receipt_uuids, list):
        return JSONResponse({"error": "Campo 'order' deve ser uma lista."}, status_code=400)

    try:
        bill_service.reorder_receipts(bill, billing, receipt_uuids)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    audit = get_audit_service(request)
    audit.safe_log(
        AuditEventType.RECEIPT_REORDER,
        actor_id=user_id,
        actor_username=request.session.get("username", ""),
        source="web",
        entity_type="bill",
        entity_id=bill.id,
        entity_uuid=bill.uuid,
        new_state={"order": receipt_uuids},
    )

    return JSONResponse({"ok": True})
