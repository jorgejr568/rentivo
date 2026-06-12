from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from rentivo.communications.render import render_markdown
from web.deps import render
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
        },
    )


@router.post("/preview")
async def communication_preview(request: Request, ctx: BillContext = Depends(require_bill("manage", json=True))):
    body = await request.json()
    return JSONResponse({"html": render_markdown(str(body.get("body", "")))})
