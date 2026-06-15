from __future__ import annotations

from datetime import date

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from rentivo.models.audit_log import AuditEventType
from rentivo.models.billing import ReadjustmentIndex
from rentivo.services.audit_serializers import serialize_billing
from rentivo.services.bcb_sgs_client import BcbSgsClient
from rentivo.services.readjustment_service import series_for_index
from rentivo.settings import settings
from web.analytics import analytics_hash, push_event
from web.deps import render
from web.flash import flash, flash_redirect
from web.guards import BillingContext, require_billing

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/billings")

_INDEX_LABELS = {
    ReadjustmentIndex.IGPM: "IGP-M",
    ReadjustmentIndex.IPCA: "IPCA",
    ReadjustmentIndex.NONE: "Nenhum",
}


def _parse_pct(raw: str) -> float | None:
    """Parse a percentage string ('10,00' or '10.00') into a float, or None."""
    text = (raw or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


@router.get("/{billing_uuid}/readjust")
async def readjust_preview(request: Request, ctx: BillingContext = Depends(require_billing("edit"))):
    billing = ctx.billing
    service = request.state.services.readjustment

    suggested_pct = None
    bcb_failed = False
    series = series_for_index(billing.readjustment_index)
    if series is not None:
        client = BcbSgsClient(base_url=settings.bcb_sgs_base_url)
        suggested_pct = await client.fetch_accumulated(series)
        bcb_failed = suggested_pct is None

    preview = service.preview(billing, suggested_pct or 0.0)
    return render(
        request,
        "billing/readjust.html",
        {
            "billing": billing,
            "preview": preview,
            "suggested_pct": suggested_pct,
            "bcb_failed": bcb_failed,
            "index_label": _INDEX_LABELS.get(billing.readjustment_index, "Nenhum"),
        },
    )


@router.post("/{billing_uuid}/readjust")
async def readjust_apply(request: Request, ctx: BillingContext = Depends(require_billing("edit"))):
    billing = ctx.billing
    service = request.state.services.readjustment

    form = await request.form()
    pct = _parse_pct(str(form.get("pct", "")))
    if pct is None:
        logger.warning("readjust_rejected", billing_uuid=billing.uuid, reason="invalid_pct")
        return flash_redirect(request, "Informe uma porcentagem válida.", f"/billings/{billing.uuid}/readjust")

    previous_state = serialize_billing(billing)
    index_value = billing.readjustment_index.value
    updated = service.apply(billing, pct=pct, applied_on=date.today())

    request.state.services.audit.safe_log_for(
        request.state.actor,
        AuditEventType.BILLING_READJUSTED,
        entity_type="billing",
        entity_id=updated.id,
        entity_uuid=updated.uuid,
        previous_state=previous_state,
        new_state=serialize_billing(updated),
        metadata={"pct": pct, "index": index_value},
    )

    flash(request, "Reajuste aplicado com sucesso!", "success")
    push_event(
        request,
        {
            "event": "rentivo_billing_readjusted",
            "billing_uuid_hash": analytics_hash(updated.uuid),
            "index": index_value,
        },
    )
    return RedirectResponse(f"/billings/{billing.uuid}", status_code=302)
