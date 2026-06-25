"""End-to-end Asaas dynamic-PIX auto-confirmation demo (REN-15 / REN-26).

Two modes:

1. ``--live`` — drive ``sandbox.asaas.com`` for real (REN-15 parent's Done
   deliverable). Requires sandbox credentials:

       export RENTIVO_ASAAS_API_KEY='<sandbox api key>'
       export RENTIVO_ASAAS_WEBHOOK_TOKEN='<shared secret you set in Asaas>'
       # base url defaults to https://api-sandbox.asaas.com/v3
       python -m rentivo.scripts.asaas_sandbox_demo --live \
           --bill-uuid <bill.uuid> --customer <asaas_customer_id> --amount-centavos 2850 0

   It: (a) creates a PIX charge (``cob``) with externalReference = bill.uuid and
   prints the copy-paste / QR; (b) settles it in the sandbox via
   ``POST /payments/{id}/receiveInCash``; (c) Asaas then POSTs a
   ``PAYMENT_RECEIVED`` webhook to your configured endpoint
   (``POST /webhooks/pix/asaas``), which auto-transitions the bill to PAID.
   Asaas must be able to reach that public URL — expose it (e.g. via a tunnel)
   and register it under Settings → Integrations → Webhooks with the same token.

2. ``--local-webhook-sim`` — credential-free proof of the *reconciliation* half.
   Builds a realistic Asaas ``PAYMENT_RECEIVED`` body and POSTs it to a running
   Rentivo instance's webhook with the shared-secret header, demonstrating the
   idempotent Bill -> PAID transition without contacting Asaas:

       export RENTIVO_ASAAS_WEBHOOK_TOKEN='dev-secret'
       python -m rentivo.scripts.asaas_sandbox_demo --local-webhook-sim \
           --base http://localhost:8000 --bill-uuid <bill.uuid> \
           --amount-centavos 2850 0 --charge-id pay_demo_1

Guardrails (REN-15): landlord-as-merchant only, sandbox credentials only, no
spend / no contract. Capture this script's stdout as the work product.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

from rentivo.services.asaas_pix_service import AsaasPixService
from rentivo.settings import settings


def _log(msg: str) -> None:
    print(msg, flush=True)


async def _run_live(args: argparse.Namespace) -> int:
    if not settings.asaas_api_key:
        _log("ERROR: RENTIVO_ASAAS_API_KEY is not set — cannot drive the sandbox.")
        return 2

    service = AsaasPixService(
        api_key=settings.asaas_api_key,
        webhook_token=settings.asaas_webhook_token,
        base_url=settings.asaas_base_url,
    )
    _log(f"== Asaas sandbox demo (base={settings.asaas_base_url}) ==")
    _log(f"Creating charge: external_reference={args.bill_uuid} amount_centavos={args.amount_centavos}")
    charge = await service.create_charge(
        external_reference=args.bill_uuid,
        amount_centavos=args.amount_centavos,
        customer_id=args.customer,
        due_date=args.due_date,
        description=args.description,
    )
    _log(f"  charge_id   = {charge.charge_id}")
    _log(f"  status      = {charge.status}")
    _log(f"  copy_paste  = {charge.copy_paste}")
    _log(f"  qr (base64) = {charge.qrcode_base64[:48]}… ({len(charge.qrcode_base64)} chars)")

    # Settle in the sandbox so Asaas emits PAYMENT_RECEIVED -> your webhook.
    _log(f"Settling charge {charge.charge_id} in sandbox via receiveInCash…")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{settings.asaas_base_url}/payments/{charge.charge_id}/receiveInCash",
            headers={"access_token": settings.asaas_api_key, "Content-Type": "application/json"},
            json={"value": round(args.amount_centavos / 100, 2), "paymentDate": args.due_date},
        )
        _log(f"  receiveInCash -> HTTP {resp.status_code}")
    _log(
        "Done. Asaas will now POST PAYMENT_RECEIVED to your configured webhook "
        "(POST /webhooks/pix/asaas); the route auto-transitions the bill to PAID.\n"
        "Verify with: SELECT status FROM bills WHERE uuid = '"
        f"{args.bill_uuid}';  (expect 'paid')"
    )
    return 0


def _run_local_webhook_sim(args: argparse.Namespace) -> int:
    token = settings.asaas_webhook_token
    if not token:
        _log("ERROR: RENTIVO_ASAAS_WEBHOOK_TOKEN is not set — the webhook would reject (fail-closed).")
        return 2

    body = {
        "id": args.event_id,
        "event": "PAYMENT_RECEIVED",
        "payment": {
            "id": args.charge_id,
            "externalReference": args.bill_uuid,
            "value": round(args.amount_centavos / 100, 2),
            "status": "RECEIVED",
            "pixTransaction": {"endToEndIdentifier": args.e2eid},
        },
    }
    url = f"{args.base.rstrip('/')}/webhooks/pix/asaas"
    _log(f"== Local webhook reconciliation demo -> {url} ==")
    _log(f"POST body: event=PAYMENT_RECEIVED externalReference={args.bill_uuid} value={body['payment']['value']}")
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(url, json=body, headers={"asaas-access-token": token})
        _log(f"  HTTP {resp.status_code}: {resp.text}")
        # Replay the exact same delivery — must be an idempotent no-op (duplicate).
        replay = client.post(url, json=body, headers={"asaas-access-token": token})
        _log(f"  replay HTTP {replay.status_code}: {replay.text}  (expect status=duplicate)")
    ok = resp.status_code == 200 and resp.json().get("status") in {"confirmed", "already_paid"}
    _log("RESULT: " + ("bill auto-confirmed [OK]" if ok else "unexpected outcome -- see output above"))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Asaas dynamic-PIX auto-confirmation demo")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="drive sandbox.asaas.com end-to-end")
    mode.add_argument("--local-webhook-sim", action="store_true", help="POST a synthetic webhook to a local instance")
    parser.add_argument("--bill-uuid", required=True, help="bill.uuid (becomes externalReference)")
    parser.add_argument("--amount-centavos", type=int, required=True, help="amount in integer centavos")
    parser.add_argument("--customer", help="Asaas sandbox customer id (live mode)")
    parser.add_argument("--due-date", default="2025-12-31", help="ISO YYYY-MM-DD")
    parser.add_argument("--description", default="", help="charge description")
    parser.add_argument("--base", default="http://localhost:8000", help="Rentivo base URL (local sim)")
    parser.add_argument("--charge-id", default="pay_demo_1", help="synthetic charge id (local sim)")
    parser.add_argument("--event-id", default="evt_demo_1", help="synthetic event id (local sim)")
    parser.add_argument("--e2eid", default="E2E-DEMO-0001", help="synthetic e2e id (local sim)")
    args = parser.parse_args(argv)

    if args.live:
        if not args.customer:
            parser.error("--live requires --customer <asaas_customer_id>")
        return asyncio.run(_run_live(args))
    return _run_local_webhook_sim(args)


if __name__ == "__main__":
    sys.exit(main())
