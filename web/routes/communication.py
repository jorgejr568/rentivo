from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from rentivo.communications.moderation import scan
from rentivo.communications.render import render_markdown
from rentivo.models.audit_log import AuditEventType
from rentivo.services.audit_serializers import serialize_communication
from web.analytics import analytics_hash, push_event
from web.deps import render
from web.flash import flash, flash_redirect
from web.guards import BillContext, require_bill

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/billings/{billing_uuid}/bills/{bill_uuid}/communications")


@router.get("/compose")
async def communication_compose(request: Request, ctx: BillContext = Depends(require_bill("manage"))):
    bill, billing = ctx.bill, ctx.billing
    services = request.state.services
    template = services.communication.resolve_template(billing, "bill_ready")
    recipients = services.recipient.list_for_billing(billing.id) if billing.id else []
    return render(
        request,
        "bill/communication_compose.html",
        {
            "bill": bill,
            "billing": billing,
            "template": template,
            "recipients": recipients,
            "role": ctx.role,
        },
    )


@router.post("/preview")
async def communication_preview(request: Request, ctx: BillContext = Depends(require_bill("manage", json=True))):
    payload = await request.json()
    subject = str(payload.get("subject", ""))
    body = str(payload.get("body", ""))
    result = scan(f"{subject}\n{body}")
    return JSONResponse({"html": render_markdown(body), "severe": list(result.severe), "mild": list(result.mild)})


@router.post("/send")
async def communication_send(request: Request, ctx: BillContext = Depends(require_bill("manage", pix=True))):
    bill, billing = ctx.bill, ctx.billing
    services = request.state.services

    bill_url = f"/billings/{billing.uuid}/bills/{bill.uuid}"
    compose_url = f"{bill_url}/communications/compose"

    if not bill.pdf_path:
        return flash_redirect(request, "Gere o PDF da fatura antes de enviar a comunicação.", bill_url)

    form = await request.form()
    subject = str(form.get("subject", "")).strip()
    body = str(form.get("body", "")).strip()
    selected = set(form.getlist("recipient_uuids"))

    all_recipients = services.recipient.list_for_billing(billing.id)
    chosen = [r for r in all_recipients if r.uuid in selected]
    if not chosen:
        return flash_redirect(request, "Selecione ao menos um destinatário.", compose_url)

    if not subject or not body:
        return flash_redirect(request, "Preencha o assunto e o corpo da mensagem.", compose_url)

    moderation = scan(f"{subject}\n{body}")
    if moderation.blocked:
        services.audit.safe_log_for(
            request.state.actor,
            AuditEventType.COMMUNICATION_BLOCKED,
            entity_type="bill",
            entity_id=bill.id,
            entity_uuid=bill.uuid,
            new_state={"severe_count": len(moderation.severe), "mild_count": len(moderation.mild)},
        )
        return flash_redirect(
            request,
            "A mensagem contém conteúdo não permitido (ofensa grave ou ameaça) e não pode ser enviada. "
            "Edite o texto destacado.",
            compose_url,
        )
    acknowledged = str(form.get("acknowledge_warning", "")).strip() != ""
    if moderation.flagged and not acknowledged:
        return flash_redirect(
            request,
            "A mensagem contém linguagem possivelmente ofensiva. Revise e marque "
            "“Reconheço e quero enviar” para continuar.",
            compose_url,
            "warning",
        )

    # The owner scope writes the user/organization-wide default template, which
    # resolve_template applies to *every* billing of that owner — so it requires
    # billing-edit authority (owner/admin), not the broader can_manage_bills
    # ("manager") gate this route runs under.
    save_scope = str(form.get("save_scope", "")).strip()
    if save_scope == "owner" and ctx.role not in ("owner", "admin"):
        return flash_redirect(
            request,
            "Você não tem permissão para salvar o modelo para toda a organização.",
            compose_url,
        )

    comms = services.communication.send(
        bill=bill,
        billing=billing,
        recipients=chosen,
        subject_template=subject,
        body_template=body,
        actor=request.state.actor,
    )

    if save_scope == "billing":
        services.communication.save_template("billing", billing.id, "bill_ready", subject, body)
    elif save_scope == "owner":
        services.communication.save_template(billing.owner_type, billing.owner_id, "bill_ready", subject, body)
    if save_scope in ("billing", "owner"):
        services.audit.safe_log_for(
            request.state.actor,
            AuditEventType.COMMUNICATION_TEMPLATE_SAVED,
            entity_type="billing",
            entity_id=billing.id,
            entity_uuid=billing.uuid,
            new_state={"scope": save_scope, "comm_type": "bill_ready"},
        )

    for comm in comms:
        services.audit.safe_log_for(
            request.state.actor,
            AuditEventType.COMMUNICATION_SENT,
            entity_type="communication",
            entity_id=comm.id,
            entity_uuid=comm.uuid,
            new_state=serialize_communication(comm),
        )

    if moderation.flagged:  # mild + acknowledged (severe already returned above)
        services.audit.safe_log_for(
            request.state.actor,
            AuditEventType.COMMUNICATION_FLAGGED_OVERRIDE,
            entity_type="bill",
            entity_id=bill.id,
            entity_uuid=bill.uuid,
            new_state={"mild_count": len(moderation.mild)},
        )

    logger.info("communications_sent", bill_uuid=bill.uuid, count=len(comms))
    flash(request, f"Comunicação enfileirada para {len(comms)} destinatário(s).", "success")
    push_event(
        request,
        {
            "event": "rentivo_communication_sent",
            "bill_uuid_hash": analytics_hash(bill.uuid),
            "recipient_count": len(comms),
            "comm_type": "bill_ready",
        },
    )
    return RedirectResponse(bill_url, status_code=302)
