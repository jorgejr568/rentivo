from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
from starlette.datastructures import UploadFile

from rentivo.communications.moderation import scan
from rentivo.models.audit_log import AuditEventType
from rentivo.models.billing import BillingItem
from rentivo.services.audit_serializers import serialize_billing, serialize_billing_attachment
from web.analytics import analytics_hash, push_event
from web.deps import render
from web.flash import flash, flash_redirect
from web.forms import parse_formset, parse_line_items
from web.guards import BillingContext, require_billing

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/billings")


def _sync_recipient_formset(
    request: Request,
    *,
    billing_id: int,
    billing_uuid: str,
    form_dict: dict,
    prefix: str,
    service_name: str,
    event_type: AuditEventType,
    count_key: str,
    track_previous: bool,
) -> None:
    """Replace a billing's recipient/reply-to formset and audit the change.

    Shared by ``billing_create`` and ``billing_edit``. The formset is only
    touched when the submission carries it (``{prefix}-TOTAL_FORMS`` present),
    so a POST that omits it leaves the existing encrypted rows intact rather
    than wiping them. ``track_previous`` adds the edit-only ``previous_state``
    and counts pre-existing rows toward the "should we audit?" decision.
    """
    if f"{prefix}-TOTAL_FORMS" not in form_dict:
        return
    service = getattr(request.state.services, service_name)
    previous = service.list_for_billing(billing_id) if track_previous else []
    rows = parse_formset(form_dict, prefix)
    saved = service.replace_for_billing(billing_id, rows)
    if not (rows or saved or previous):
        return
    new_state = {count_key: len(saved)}
    previous_state = {count_key: len(previous)} if track_previous else None
    request.state.services.audit.safe_log_for(
        request.state.actor,
        event_type,
        entity_type="billing",
        entity_id=billing_id,
        entity_uuid=billing_uuid,
        previous_state=previous_state,
        new_state=new_state,
    )


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
    reminders_enabled = str(form.get("reminders_enabled", "")).strip() == "1"

    if not name:
        logger.warning("billing_create_rejected", reason="empty_name")
        return flash_redirect(request, "Nome é obrigatório.", "/billings/create")

    items: list[BillingItem] = [
        BillingItem(description=p.description, amount=p.amount, item_type=p.item_type)
        for p in parse_line_items(dict(form), "items", amount_only_for_fixed=True)
    ]

    if not items:
        logger.warning("billing_create_rejected", reason="no_items")
        return flash_redirect(request, "Adicione pelo menos um item.", "/billings/create")

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
            reminders_enabled=reminders_enabled,
        )
    except ValueError as e:
        return flash_redirect(request, str(e), "/billings/create")

    audit = request.state.services.audit
    audit.safe_log_for(
        request.state.actor,
        AuditEventType.BILLING_CREATE,
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        new_state=serialize_billing(billing),
    )

    # Only touch recipients/reply-to when the submission carries the formset,
    # so the behaviour is identical across create and edit.
    form_dict = dict(form)
    _sync_recipient_formset(
        request,
        billing_id=billing.id,
        billing_uuid=billing.uuid,
        form_dict=form_dict,
        prefix="recipients",
        service_name="recipient",
        event_type=AuditEventType.BILLING_RECIPIENTS_UPDATED,
        count_key="recipient_count",
        track_previous=False,
    )
    _sync_recipient_formset(
        request,
        billing_id=billing.id,
        billing_uuid=billing.uuid,
        form_dict=form_dict,
        prefix="reply_to",
        service_name="reply_to",
        event_type=AuditEventType.BILLING_REPLY_TO_UPDATED,
        count_key="reply_to_count",
        track_previous=False,
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
        return flash_redirect(request, "Cobrança inválida.", "/")

    bills = bill_service.list_bills(billing.id)

    expenses = request.state.services.expense.list_for_billing(billing.id)
    stats = request.state.services.billing_stats.stats_for_ids([billing.id])

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
            "expenses": expenses,
            "stats": stats,
            "role": ctx.role,
            "user_orgs": user_orgs,
            "pix_needs_setup": pix_needs_setup,
            "attachments": request.state.services.billing_attachment.list_attachments(billing.id),
        },
    )


@router.get("/{billing_uuid}/edit")
async def billing_edit_form(request: Request, ctx: BillingContext = Depends(require_billing("edit"))):
    recipients = request.state.services.recipient.list_for_billing(ctx.billing.id) if ctx.billing.id else []
    reply_to = request.state.services.reply_to.list_for_billing(ctx.billing.id) if ctx.billing.id else []
    attachments = request.state.services.billing_attachment.list_attachments(ctx.billing.id) if ctx.billing.id else []
    reminder_template = request.state.services.communication.resolve_template(ctx.billing, "payment_reminder")
    return render(
        request,
        "billing/edit.html",
        {
            "billing": ctx.billing,
            "recipients": recipients,
            "reply_to": reply_to,
            "attachments": attachments,
            "reminder_template": reminder_template,
            "role": ctx.role,
        },
    )


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
    billing.reminders_enabled = str(form.get("reminders_enabled", "")).strip() == "1"

    items: list[BillingItem] = [
        BillingItem(description=p.description, amount=p.amount, item_type=p.item_type)
        for p in parse_line_items(dict(form), "items", amount_only_for_fixed=True)
    ]

    if not items:
        logger.warning("billing_edit_rejected", billing_uuid=billing.uuid, reason="no_items")
        return flash_redirect(request, "A cobrança precisa de pelo menos um item.", f"/billings/{billing.uuid}/edit")

    billing.items = items
    try:
        updated = service.update_billing(billing)
    except ValueError as e:
        return flash_redirect(request, str(e), f"/billings/{billing.uuid}/edit")

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

    # Replacing recipients is destructive (delete-all + re-insert), so a POST
    # that omits the formset entirely (a stale cached form, a non-recipient-aware
    # client) must leave the existing encrypted recipients intact rather than
    # silently wiping them as a side effect of an unrelated field edit.
    form_dict = dict(form)
    _sync_recipient_formset(
        request,
        billing_id=updated.id,
        billing_uuid=updated.uuid,
        form_dict=form_dict,
        prefix="recipients",
        service_name="recipient",
        event_type=AuditEventType.BILLING_RECIPIENTS_UPDATED,
        count_key="recipient_count",
        track_previous=True,
    )
    _sync_recipient_formset(
        request,
        billing_id=updated.id,
        billing_uuid=updated.uuid,
        form_dict=form_dict,
        prefix="reply_to",
        service_name="reply_to",
        event_type=AuditEventType.BILLING_REPLY_TO_UPDATED,
        count_key="reply_to_count",
        track_previous=True,
    )

    flash(request, "Cobrança atualizada com sucesso!", "success")
    push_event(request, {"event": "rentivo_billing_edited", "billing_uuid_hash": analytics_hash(updated.uuid)})
    return RedirectResponse(f"/billings/{billing.uuid}", status_code=302)


@router.post("/{billing_uuid}/reminder-template")
async def billing_reminder_template(request: Request, ctx: BillingContext = Depends(require_billing("edit"))):
    """Save the per-billing (or owner-wide) ``payment_reminder`` template copy.

    Mirrors the ``bill_ready`` save flow in ``communication.py`` so the reminder
    email resolves billing → owner → system default exactly like the invoice
    email, and runs the same moderation gate since the copy is sent automatically.
    """
    billing = ctx.billing
    services = request.state.services
    redirect_url = f"/billings/{billing.uuid}/edit"

    form = await request.form()
    subject = str(form.get("subject", "")).strip()
    body = str(form.get("body", "")).strip()
    if not subject or not body:
        return flash_redirect(request, "Preencha o assunto e o corpo do lembrete.", redirect_url)

    moderation = scan(f"{subject}\n{body}")
    if moderation.blocked:
        return flash_redirect(
            request,
            "O modelo contém conteúdo não permitido (ofensa grave ou ameaça). Edite o texto antes de salvar.",
            redirect_url,
        )

    # Owner scope writes the user/organization-wide default applied to *every*
    # billing of that owner, so it requires owner/admin authority.
    save_scope = str(form.get("save_scope", "")).strip() or "billing"
    if save_scope == "owner" and ctx.role not in ("owner", "admin"):
        return flash_redirect(
            request,
            "Você não tem permissão para salvar o modelo para toda a organização.",
            redirect_url,
        )

    if save_scope == "owner":
        services.communication.save_template(billing.owner_type, billing.owner_id, "payment_reminder", subject, body)
    else:
        services.communication.save_template("billing", billing.id, "payment_reminder", subject, body)

    services.audit.safe_log_for(
        request.state.actor,
        AuditEventType.COMMUNICATION_TEMPLATE_SAVED,
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        new_state={"scope": save_scope, "comm_type": "payment_reminder"},
    )

    flash(request, "Modelo de lembrete de pagamento salvo.", "success")
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/{billing_uuid}/transfer")
async def billing_transfer(request: Request, ctx: BillingContext = Depends(require_billing("transfer"))):
    billing = ctx.billing
    billing_service = request.state.services.billing

    form = await request.form()
    org_id_raw = str(form.get("organization_id", "")).strip()
    if not org_id_raw:
        return flash_redirect(request, "Selecione uma organização.", f"/billings/{billing.uuid}")
    try:
        org_id = int(org_id_raw)
    except ValueError:
        return flash_redirect(request, "Organização inválida.", f"/billings/{billing.uuid}")

    org_service = request.state.services.organization
    if org_service.get_member(org_id, ctx.user_id) is None:
        logger.warning(
            "billing_transfer_rejected",
            billing_uuid=billing.uuid,
            org_id=org_id,
            reason="not_member",
        )
        return flash_redirect(request, "Você não é membro dessa organização.", f"/billings/{billing.uuid}")

    previous_owner = {"owner_type": billing.owner_type, "owner_id": billing.owner_id}
    try:
        billing_service.transfer_to_organization(billing.id, org_id)
    except ValueError as e:
        return flash_redirect(request, str(e), f"/billings/{billing.uuid}")

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
        return flash_redirect(request, "Cobrança inválida.", "/")
    previous_state = serialize_billing(billing)

    cleanup = request.state.services.storage_cleanup
    cleanup.enqueue_billing_delete_cascade(request.state.actor, billing)

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


@router.post("/{billing_uuid}/attachments/upload")
async def attachment_upload(request: Request, ctx: BillingContext = Depends(require_billing("edit"))):
    billing = ctx.billing
    service = request.state.services.billing_attachment
    redirect_url = f"/billings/{billing.uuid}/edit"

    form = await request.form()
    upload = form.get("attachment_file")
    name = str(form.get("name", ""))
    if not isinstance(upload, UploadFile) or not upload.filename:
        return flash_redirect(request, "Nenhum arquivo selecionado.", redirect_url)

    file_bytes = await upload.read()
    # The service is the single source of file validation (type / size / empty).
    try:
        attachment = service.add_attachment(
            billing=billing,
            name=name,
            filename=upload.filename,
            file_bytes=file_bytes,
            content_type=upload.content_type or "",
        )
    except ValueError as e:
        logger.warning("attachment_upload_rejected", billing_uuid=billing.uuid, error=str(e))
        return flash_redirect(request, "Arquivo inválido (tipo não suportado, vazio ou maior que 10 MB).", redirect_url)

    request.state.services.audit.safe_log_for(
        request.state.actor,
        AuditEventType.ATTACHMENT_UPLOAD,
        entity_type="billing_attachment",
        entity_id=attachment.id,
        entity_uuid=attachment.uuid,
        new_state=serialize_billing_attachment(attachment, billing_uuid=billing.uuid),
    )
    flash(request, "Documento anexado.", "success")
    push_event(
        request,
        {"event": "rentivo_billing_attachment_uploaded", "billing_uuid_hash": analytics_hash(billing.uuid)},
    )
    return RedirectResponse(redirect_url, status_code=302)


@router.get("/{billing_uuid}/attachments/{attachment_uuid}")
async def attachment_download(
    request: Request, attachment_uuid: str, ctx: BillingContext = Depends(require_billing("view"))
):
    service = request.state.services.billing_attachment
    attachment = service.get_attachment_by_uuid(attachment_uuid)
    if not attachment or not attachment.storage_key or attachment.billing_id != ctx.billing.id:
        return flash_redirect(request, "Documento não encontrado.", "/")

    ref = service.get_attachment_ref(attachment)
    if ref.kind == "local":
        return FileResponse(ref.location, media_type=attachment.content_type)
    return RedirectResponse(ref.location, status_code=302)


@router.post("/{billing_uuid}/attachments/{attachment_uuid}/delete")
async def attachment_delete(
    request: Request, attachment_uuid: str, ctx: BillingContext = Depends(require_billing("edit"))
):
    billing = ctx.billing
    service = request.state.services.billing_attachment
    redirect_url = f"/billings/{billing.uuid}/edit"

    attachment = service.get_attachment_by_uuid(attachment_uuid)
    if not attachment or attachment.billing_id != billing.id:
        return flash_redirect(request, "Documento não encontrado.", redirect_url)

    previous_state = serialize_billing_attachment(attachment, billing_uuid=billing.uuid)
    service.delete_attachment(attachment)
    request.state.services.storage_cleanup.enqueue_attachment_delete(request.state.actor, attachment)
    request.state.services.audit.safe_log_for(
        request.state.actor,
        AuditEventType.ATTACHMENT_DELETE,
        entity_type="billing_attachment",
        entity_id=attachment.id,
        entity_uuid=attachment.uuid,
        previous_state=previous_state,
    )
    flash(request, "Documento removido.", "success")
    push_event(
        request,
        {"event": "rentivo_billing_attachment_deleted", "billing_uuid_hash": analytics_hash(billing.uuid)},
    )
    return RedirectResponse(redirect_url, status_code=302)
