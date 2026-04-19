from __future__ import annotations

import os

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.datastructures import UploadFile

from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import BillLineItem
from rentivo.models.billing import ItemType
from rentivo.models.receipt import ALLOWED_RECEIPT_TYPES, MAX_RECEIPT_SIZE
from rentivo.services.audit_serializers import serialize_bill
from web.deps import (
    get_audit_service,
    get_authorization_service,
    get_bill_service,
    get_billing_service,
    get_pix_service,
    render,
)
from web.flash import flash
from web.forms import parse_brl, parse_formset

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/billings/{billing_uuid}/bills")


@router.get("/generate")
async def bill_generate_form(request: Request, billing_uuid: str):
    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)
    billing = billing_service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("billing_not_found", billing_uuid=billing_uuid)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)
    user_id = request.session.get("user_id")
    if not auth_service.can_manage_bills(user_id, billing):
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)
    if get_pix_service(request).billing_needs_setup(billing):
        flash(
            request,
            "Configure a chave PIX, o nome e a cidade do recebedor antes de gerar faturas.",
            "warning",
        )
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)
    return render(request, "bill/generate.html", {"billing": billing})


@router.post("/generate")
async def bill_generate(request: Request, billing_uuid: str):
    billing_service = get_billing_service(request)
    bill_service = get_bill_service(request)
    auth_service = get_authorization_service(request)

    billing = billing_service.get_billing_by_uuid(billing_uuid)
    if not billing:
        logger.warning("billing_not_found", billing_uuid=billing_uuid)
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
        logger.warning("bill_generate_rejected", reason="empty_reference_month")
        flash(request, "Mês de referência é obrigatório.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}/bills/generate", status_code=302)

    if get_pix_service(request).billing_needs_setup(billing):
        logger.warning("bill_generate_rejected", billing_uuid=billing_uuid, reason="pix_not_configured")
        flash(
            request,
            "Configure a chave PIX, o nome e a cidade do recebedor antes de gerar faturas.",
            "warning",
        )
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)

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

    bill = bill_service.generate_bill(
        billing=billing,
        reference_month=reference_month,
        variable_amounts=variable_amounts,
        extras=extras,
        notes=notes,
        due_date=due_date,
    )

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
        receipt, _ = bill_service.add_receipt(
            bill=bill,
            billing=billing,
            filename=upload.filename,
            file_bytes=file_bytes,
            content_type=content_type,
        )
        attached_receipts.append(receipt)
    if attached_receipts:
        logger.info("receipts_attached", bill_uuid=bill.uuid, count=len(attached_receipts))

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
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("bill_not_found", bill_uuid=bill_uuid)
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        logger.warning("billing_not_found_for_bill", billing_id=bill.billing_id)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    user_id = request.session.get("user_id")
    if not auth_service.can_view_billing(user_id, billing):
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse("/", status_code=302)

    role = auth_service.get_role_for_billing(user_id, billing)
    receipts = bill_service.list_receipts(bill.id) if bill.id else []
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
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("bill_not_found", bill_uuid=bill_uuid)
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        logger.warning("billing_not_found_for_bill", billing_id=bill.billing_id)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)
    receipts = bill_service.list_receipts(bill.id) if bill.id else []
    return render(request, "bill/edit.html", {"bill": bill, "billing": billing, "receipts": receipts})


@router.post("/{bill_uuid}/edit")
async def bill_edit(request: Request, billing_uuid: str, bill_uuid: str):
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("bill_not_found", bill_uuid=bill_uuid)
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        logger.warning("billing_not_found_for_bill", billing_id=bill.billing_id)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    if get_pix_service(request).billing_needs_setup(billing):
        flash(
            request,
            "Configure a chave PIX, o nome e a cidade do recebedor antes de editar esta fatura.",
            "warning",
        )
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)

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

    bill = bill_service.update_bill(
        bill=bill,
        billing=billing,
        line_items=line_items,
        notes=notes,
        due_date=due_date,
    )

    user_id = request.session.get("user_id")
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
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("bill_not_found", bill_uuid=bill_uuid)
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        logger.warning("billing_not_found_for_bill", billing_id=bill.billing_id)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    if get_pix_service(request).billing_needs_setup(billing):
        flash(
            request,
            "Configure a chave PIX, o nome e a cidade do recebedor antes de regenerar o PDF.",
            "warning",
        )
        return RedirectResponse(f"/billings/{billing_uuid}/bills/{bill_uuid}", status_code=302)

    old_pdf_path = bill.pdf_path
    bill_service.regenerate_pdf(bill, billing)

    user_id = request.session.get("user_id")
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
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("bill_not_found", bill_uuid=bill_uuid)
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    user_id = request.session.get("user_id")
    if not auth_service.can_manage_bills(user_id, billing):
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)

    form = await request.form()
    new_status = str(form.get("status", "")).strip()
    previous_status = bill.status

    try:
        bill_service.change_status(bill, new_status)
    except ValueError:
        flash(request, "Status inválido.", "danger")
        return RedirectResponse(f"/billings/{billing_uuid}/bills/{bill_uuid}", status_code=302)

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
    bill_service = get_bill_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("bill_not_found", bill_uuid=bill_uuid)
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    if bill.id is None:
        logger.error("bill_missing_id", bill_uuid=bill_uuid)
        flash(request, "Fatura inválida.", "danger")
        return RedirectResponse("/", status_code=302)
    previous_state = serialize_bill(bill)
    bill_service.delete_bill(bill.id)

    user_id = request.session.get("user_id")
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
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill or not bill.pdf_path:
        logger.warning("bill_no_pdf", bill_uuid=bill_uuid)
        flash(request, "Fatura sem PDF.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        logger.warning("billing_not_found_for_bill", billing_id=bill.billing_id)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    user_id = request.session.get("user_id")
    if not auth_service.can_view_billing(user_id, billing):
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse("/", status_code=302)

    logger.debug("bill_pdf_path", storage_key=bill.pdf_path)

    # Local storage: serve file directly. S3: redirect to presigned URL.
    if os.path.isfile(bill.pdf_path):
        return FileResponse(bill.pdf_path, media_type="application/pdf")

    url = bill_service.get_invoice_url(bill.pdf_path)

    return RedirectResponse(url, status_code=302)


@router.get("/{bill_uuid}/receipts/{receipt_uuid}")
async def receipt_view(request: Request, billing_uuid: str, bill_uuid: str, receipt_uuid: str):
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)

    receipt = bill_service.get_receipt_by_uuid(receipt_uuid)
    if not receipt or not receipt.storage_key:
        flash(request, "Comprovante não encontrado.", "danger")
        return RedirectResponse("/", status_code=302)

    bill = bill_service.get_bill(receipt.bill_id)
    if not bill or bill.uuid != bill_uuid:
        flash(request, "Comprovante não encontrado.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing or billing.uuid != billing_uuid:
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    user_id = request.session.get("user_id")
    if not auth_service.can_view_billing(user_id, billing):
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse("/", status_code=302)

    url_or_path = bill_service.storage.get_url(receipt.storage_key)

    if os.path.isfile(url_or_path):
        return FileResponse(url_or_path, media_type=receipt.content_type)

    return RedirectResponse(url_or_path, status_code=302)


@router.post("/{bill_uuid}/receipts/upload")
async def receipt_upload(request: Request, billing_uuid: str, bill_uuid: str):
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)

    form = await request.form()
    redirect_url = str(form.get("next", "")).strip() or f"/billings/{billing_uuid}/bills/{bill_uuid}/edit"

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("bill_not_found", bill_uuid=bill_uuid)
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        logger.warning("billing_not_found_for_bill", billing_id=bill.billing_id)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    uploads = form.getlist("receipt_files")
    valid_uploads = [u for u in uploads if isinstance(u, UploadFile) and u.filename]
    if not valid_uploads:
        logger.warning("receipt_upload_no_file", bill_uuid=bill_uuid)
        flash(request, "Nenhum arquivo selecionado.", "danger")
        return RedirectResponse(redirect_url, status_code=302)

    if get_pix_service(request).billing_needs_setup(billing):
        flash(
            request,
            "Configure a chave PIX, o nome e a cidade do recebedor antes de anexar comprovantes.",
            "warning",
        )
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)

    attached = 0
    skipped = 0
    accumulated_failed: set[str] = set()
    audit = get_audit_service(request)
    for upload in valid_uploads:
        file_bytes = await upload.read()
        content_type = upload.content_type or ""

        if content_type not in ALLOWED_RECEIPT_TYPES:
            logger.warning("receipt_upload_invalid_type", content_type=content_type)
            skipped += 1
            continue
        if not file_bytes:
            skipped += 1
            continue
        if len(file_bytes) > MAX_RECEIPT_SIZE:
            skipped += 1
            continue

        receipt, failed_uuids = bill_service.add_receipt(
            bill=bill,
            billing=billing,
            filename=upload.filename,
            file_bytes=file_bytes,
            content_type=content_type,
        )

        attached += 1
        accumulated_failed.update(failed_uuids)

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
    if accumulated_failed:
        flash(
            request,
            f"{len(accumulated_failed)} comprovante(s) não puderam ser incluídos no PDF. Tente enviar novamente.",
            "warning",
        )
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/{bill_uuid}/receipts/{receipt_uuid}/delete")
async def receipt_delete(request: Request, billing_uuid: str, bill_uuid: str, receipt_uuid: str):
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)

    form = await request.form()
    redirect_url = str(form.get("next", "")).strip() or f"/billings/{billing_uuid}/bills/{bill_uuid}/edit"

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        logger.warning("bill_not_found", bill_uuid=bill_uuid)
        flash(request, "Fatura não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing or billing.uuid != billing_uuid:
        logger.warning("billing_not_found_for_bill", billing_id=bill.billing_id)
        flash(request, "Cobrança não encontrada.", "danger")
        return RedirectResponse("/", status_code=302)

    user_id = request.session.get("user_id")
    if not auth_service.can_manage_bills(user_id, billing):
        logger.warning("receipt_delete_access_denied", bill_uuid=bill_uuid, user_id=user_id)
        flash(request, "Acesso negado.", "danger")
        return RedirectResponse("/", status_code=302)

    receipt = bill_service.get_receipt_by_uuid(receipt_uuid)
    if not receipt or receipt.bill_id != bill.id:
        logger.warning("receipt_not_found", receipt_uuid=receipt_uuid)
        flash(request, "Comprovante não encontrado.", "danger")
        return RedirectResponse(redirect_url, status_code=302)

    if get_pix_service(request).billing_needs_setup(billing):
        flash(
            request,
            "Configure a chave PIX, o nome e a cidade do recebedor antes de remover comprovantes.",
            "warning",
        )
        return RedirectResponse(f"/billings/{billing_uuid}", status_code=302)

    previous_state = {
        "filename": receipt.filename,
        "content_type": receipt.content_type,
        "file_size": receipt.file_size,
        "bill_uuid": bill_uuid,
        "billing_uuid": billing_uuid,
    }
    bill_service.delete_receipt(receipt, bill, billing)

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
    bill_service = get_bill_service(request)
    billing_service = get_billing_service(request)
    auth_service = get_authorization_service(request)

    bill = bill_service.get_bill_by_uuid(bill_uuid)
    if not bill:
        return JSONResponse({"error": "Fatura não encontrada."}, status_code=404)

    billing = billing_service.get_billing(bill.billing_id)
    if not billing:
        return JSONResponse({"error": "Cobrança não encontrada."}, status_code=404)

    user_id = request.session.get("user_id")
    if not auth_service.can_manage_bills(user_id, billing):
        return JSONResponse({"error": "Acesso negado."}, status_code=403)

    if get_pix_service(request).billing_needs_setup(billing):
        return JSONResponse(
            {"error": "Configure a chave PIX, o nome e a cidade do recebedor antes de reordenar comprovantes."},
            status_code=400,
        )

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
