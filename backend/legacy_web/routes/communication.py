from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from legacy_web.analytics import analytics_hash, push_event
from legacy_web.deps import render
from legacy_web.flash import flash, flash_redirect
from legacy_web.guards import BillContext, require_bill
from rentivo.communications.moderation import scan
from rentivo.communications.render import render_markdown
from rentivo.models.audit_log import AuditEventType
from rentivo.models.communication import CommType
from rentivo.services.audit_serializers import serialize_communication

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/billings/{billing_uuid}/bills/{bill_uuid}/communications")


def _parse_comm_type(raw: str) -> CommType | None:
    """Strictly parse a communication type — no silent default, so a bad value is
    rejected instead of coerced into sending the wrong document."""
    try:
        return CommType(raw.strip())
    except ValueError:
        return None


@router.get("/compose")
async def communication_compose(request: Request, ctx: BillContext = Depends(require_bill("manage"))):
    bill, billing = ctx.bill, ctx.billing
    services = request.state.services
    bill_url = f"/billings/{billing.uuid}/bills/{bill.uuid}"

    comm_type = _parse_comm_type(str(request.query_params.get("type", "")))
    if comm_type is None:
        return flash_redirect(request, "Tipo de comunicação inválido.", bill_url)
    if comm_type is CommType.PAYMENT_RECEIPT and not bill.recibo_pdf_path:
        return flash_redirect(
            request,
            "O recibo ainda não está disponível. Ele é gerado quando a fatura é marcada como paga.",
            bill_url,
        )

    template = services.communication.resolve_template(billing, comm_type.value)
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
            "comm_type": comm_type.value,
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

    form = await request.form()
    comm_type = _parse_comm_type(str(form.get("comm_type", "")))
    if comm_type is None:
        return flash_redirect(request, "Tipo de comunicação inválido.", bill_url)
    compose_url = f"{bill_url}/communications/compose?type={comm_type.value}"

    if comm_type is CommType.PAYMENT_RECEIPT:
        if not bill.recibo_pdf_path:
            return flash_redirect(request, "O recibo ainda não está disponível para envio.", bill_url)
    elif not bill.pdf_path:
        return flash_redirect(request, "Gere o PDF da fatura antes de enviar a comunicação.", bill_url)

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
        comm_type=comm_type.value,
    )

    if save_scope == "billing":
        services.communication.save_template("billing", billing.id, comm_type.value, subject, body)
    elif save_scope == "owner":
        services.communication.save_template(billing.owner_type, billing.owner_id, comm_type.value, subject, body)
    if save_scope in ("billing", "owner"):
        services.audit.safe_log_for(
            request.state.actor,
            AuditEventType.COMMUNICATION_TEMPLATE_SAVED,
            entity_type="billing",
            entity_id=billing.id,
            entity_uuid=billing.uuid,
            new_state={"scope": save_scope, "comm_type": comm_type.value},
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
            "comm_type": comm_type.value,
        },
    )
    return RedirectResponse(bill_url, status_code=302)
