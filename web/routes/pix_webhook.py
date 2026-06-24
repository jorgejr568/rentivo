"""Public PSP payment-webhook endpoint — Asaas dynamic-PIX (REN-26).

Unauthenticated at the network edge (the PSP cannot present a session cookie),
but every delivery is authenticated by a constant-time shared-secret check on
the ``asaas-access-token`` header before any work happens. Replay protection /
idempotency live in :class:`PixReconciliationService` via the
``pix_webhook_events`` ledger.

Security posture (signature/shared-secret verification, replay protection,
idempotency, public-route exposure) is owned by SecurityAnalyst (REN-27) before
any non-sandbox use. This route is mounted under ``/webhooks``, which is
allow-listed past auth/MFA/CSRF in ``web/deps.py`` and ``web/csrf.py``.

Webhook contract: we ack ``200`` for every delivery we durably handle — including
replays, unknown bills, and amount mismatches — so the PSP stops retrying. We
return non-2xx only for an unauthenticated caller (``401``) or an unparseable
body (``400``), both of which are genuine "do not record" conditions.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks")

# Asaas sends the caller-configured shared secret in this header (lower-cased by
# ASGI). It is NOT a signature — verification is a constant-time equality check.
ASAAS_TOKEN_HEADER = "asaas-access-token"


@router.post("/pix/asaas")
async def asaas_pix_webhook(request: Request) -> JSONResponse:
    service = request.state.services.asaas_pix

    # Fail closed: if the integration is not configured, do not expose a live
    # public endpoint that silently accepts payloads.
    if not service.is_enabled:
        logger.warning("asaas_webhook_disabled")
        return JSONResponse({"status": "disabled"}, status_code=503)

    # 1. Authenticate the delivery (constant-time, fail-closed) BEFORE reading
    #    the body, so an unauthenticated caller cannot drive any side effect.
    token = request.headers.get(ASAAS_TOKEN_HEADER)
    if not service.verify_webhook_token(token):
        logger.warning("asaas_webhook_unauthorized")
        return JSONResponse({"status": "unauthorized"}, status_code=401)

    # 2. Parse the JSON body.
    try:
        body = await request.json()
    except Exception:
        logger.warning("asaas_webhook_bad_json")
        return JSONResponse({"status": "bad_request"}, status_code=400)

    event = service.parse_webhook(body)
    if event is None:
        # Authenticated but not a payment event we can act on (e.g. a
        # subscription notification). Ack so the PSP stops retrying.
        logger.info(
            "asaas_webhook_unactionable_event", event=str(body.get("event")) if isinstance(body, dict) else None
        )
        return JSONResponse({"status": "ignored"})

    # 3. Reconcile (idempotent; drives Bill -> PAID through the single chokepoint).
    result = request.state.services.pix_reconciliation.confirm_payment(event)
    logger.info("asaas_webhook_processed", outcome=result.outcome.value, bill_uuid=result.bill_uuid)
    return JSONResponse({"status": result.outcome.value, "bill_uuid": result.bill_uuid})
