"""Asaas dynamic-PIX provider client (REN-15 sandbox pilot).

Implements the *landlord-as-merchant* dynamic-PIX flow against the Asaas
sandbox: create a charge (``cob``), fetch its copy-paste / QR payload, and
parse + authenticate the inbound payment webhook so a reconciliation job can
move the matching :class:`~rentivo.models.bill.Bill` to ``PAID``.

Design notes
------------
* **Provider-agnostic seam.** Callers depend on the :class:`PixProvider`
  protocol, not on Asaas directly, so Efí / Mercado Pago can be slotted in
  later (per the REN-5 spike) without touching the webhook route or the
  reconciliation job.
* **Reconciliation key.** We set ``externalReference = bill.uuid`` when
  creating the charge. Asaas echoes it back on every webhook, giving a
  deterministic charge->bill key without round-tripping the BR-code ``txid``.
  We also persist the Asaas ``payment id`` and the PIX end-to-end id
  (``e2eid``) for audit / dedup.
* **Webhook authentication.** Asaas does not HMAC-sign webhooks; it sends a
  caller-configured shared secret in the ``asaas-access-token`` header. We
  verify it in constant time. Replay protection + idempotency live in the
  reconciliation layer, keyed on the Asaas event id / e2eid. The full webhook
  security posture is owned by SecurityAnalyst (REN-15 child issue) before any
  non-sandbox use.
* **HTTP injection.** Mirrors :class:`TurnstileService`: an injectable async
  client factory keeps the network out of unit tests.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

import structlog

from rentivo.observability import traced

logger = structlog.get_logger(__name__)

# Asaas webhook event types that mean "money has actually arrived". Both fire
# for a PIX charge: PAYMENT_RECEIVED (cash-in detected) and PAYMENT_CONFIRMED
# (settled). We treat either as a paid signal — the reconciliation layer's
# idempotency guard collapses the duplicate into a single bill transition.
PAID_EVENT_TYPES: frozenset[str] = frozenset({"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"})


class _AsyncHttpResponse(Protocol):
    def json(self) -> dict: ...
    def raise_for_status(self) -> None: ...


class _AsyncHttpClient(Protocol):
    async def post(self, url: str, *, headers: dict[str, str], json: dict, timeout: float) -> _AsyncHttpResponse: ...
    async def get(self, url: str, *, headers: dict[str, str], timeout: float) -> _AsyncHttpResponse: ...
    async def aclose(self) -> None: ...


HttpClientFactory = Callable[[], _AsyncHttpClient]


@dataclass(frozen=True)
class PixCharge:
    """A created dynamic-PIX charge ready to present to the tenant."""

    charge_id: str  # provider charge id (Asaas payment id)
    external_reference: str  # our reconciliation key (bill.uuid)
    copy_paste: str  # BR-code "pix copia e cola" string
    qrcode_base64: str  # PNG QR as base64 (no data: prefix)
    amount_centavos: int
    status: str  # provider status at creation (e.g. "PENDING")
    expiration: str | None = None  # ISO-8601, when the QR expires (if provided)


@dataclass(frozen=True)
class PixPaymentEvent:
    """A normalized inbound payment webhook event."""

    event_id: str  # provider event id — replay/idempotency key
    event_type: str  # raw provider event type (e.g. "PAYMENT_RECEIVED")
    charge_id: str  # provider charge id (Asaas payment id)
    external_reference: str  # our reconciliation key (bill.uuid)
    amount_centavos: int
    status: str  # provider payment status (e.g. "RECEIVED", "CONFIRMED")
    e2eid: str | None = None  # PIX end-to-end id, when present

    @property
    def is_paid(self) -> bool:
        return self.event_type in PAID_EVENT_TYPES


class ProviderError(RuntimeError):
    """Raised when the PSP API call fails or returns an unusable response."""


class PixProvider(Protocol):
    """Provider-agnostic dynamic-PIX seam (Asaas today; Efí/MP swappable)."""

    @property
    def provider_name(self) -> str: ...

    async def create_charge(
        self, *, external_reference: str, amount_centavos: int, customer_id: str, due_date: str, description: str = ""
    ) -> PixCharge: ...

    def verify_webhook_token(self, token: str | None) -> bool: ...

    def parse_webhook(self, body: dict[str, Any]) -> PixPaymentEvent | None: ...


def _centavos_to_brl(centavos: int) -> float:
    """Asaas expects a decimal BRL value; convert from integer centavos."""
    if centavos < 0:
        raise ValueError("amount_centavos must be non-negative")
    return round(centavos / 100, 2)


def _brl_to_centavos(value: Any) -> int:
    """Convert an Asaas decimal BRL value back to integer centavos safely."""
    try:
        # Use string round-trip to avoid binary-float drift (e.g. 1500.00).
        return int(round(float(value) * 100))
    except TypeError, ValueError:
        return 0


class AsaasPixService:
    """Asaas dynamic-PIX client (sandbox-first).

    The service is a no-op unless an API key is configured (``is_enabled``),
    so the rest of the app can wire it unconditionally and gate on the flag —
    matching the TurnstileService convention.
    """

    def __init__(
        self,
        *,
        api_key: str,
        webhook_token: str,
        base_url: str = "https://api-sandbox.asaas.com/v3",
        http_client_factory: HttpClientFactory | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._webhook_token = webhook_token
        self._base_url = base_url.rstrip("/")
        self._factory = http_client_factory or self._default_factory
        self._timeout = timeout

    @staticmethod
    def _default_factory() -> _AsyncHttpClient:
        import httpx

        return httpx.AsyncClient(timeout=10.0)

    @property
    def provider_name(self) -> str:
        return "asaas"

    @property
    def is_enabled(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        return {"access_token": self._api_key, "Content-Type": "application/json"}

    @traced("asaas.create_charge")
    async def create_charge(
        self,
        *,
        external_reference: str,
        amount_centavos: int,
        customer_id: str,
        due_date: str,
        description: str = "",
    ) -> PixCharge:
        """Create a PIX charge and fetch its copy-paste / QR payload.

        ``external_reference`` is the reconciliation key (use ``bill.uuid``).
        ``customer_id`` is the Asaas customer id the charge is billed to;
        ``due_date`` is ISO ``YYYY-MM-DD``.
        """
        if not self.is_enabled:
            raise ProviderError("Asaas API key not configured")

        client = self._factory()
        try:
            payment = await self._post(
                client,
                "/payments",
                {
                    "customer": customer_id,
                    "billingType": "PIX",
                    "value": _centavos_to_brl(amount_centavos),
                    "dueDate": due_date,
                    "externalReference": external_reference,
                    "description": description or f"Rentivo bill {external_reference}",
                },
            )
            charge_id = str(payment.get("id") or "")
            if not charge_id:
                raise ProviderError("Asaas payment response missing id")

            qr = await self._get(client, f"/payments/{charge_id}/pixQrCode")
        finally:
            await self._aclose(client)

        copy_paste = str(qr.get("payload") or "")
        if not copy_paste:
            raise ProviderError("Asaas pixQrCode response missing payload")

        charge = PixCharge(
            charge_id=charge_id,
            external_reference=external_reference,
            copy_paste=copy_paste,
            qrcode_base64=str(qr.get("encodedImage") or ""),
            amount_centavos=amount_centavos,
            status=str(payment.get("status") or "PENDING"),
            expiration=qr.get("expirationDate"),
        )
        logger.info(
            "asaas_charge_created",
            charge_id=charge_id,
            external_reference=external_reference,
            amount_centavos=amount_centavos,
        )
        return charge

    @traced("asaas.verify_webhook_token")
    def verify_webhook_token(self, token: str | None) -> bool:
        """Constant-time check of the Asaas ``asaas-access-token`` header.

        When no token is configured the webhook is rejected (fail closed) —
        an unauthenticated public payment webhook must never be accepted.
        """
        if not self._webhook_token:
            logger.warning("asaas_webhook_token_unconfigured")
            return False
        if not token:
            return False
        return hmac.compare_digest(token, self._webhook_token)

    @traced("asaas.parse_webhook")
    def parse_webhook(self, body: dict[str, Any]) -> PixPaymentEvent | None:
        """Normalize an Asaas webhook body into a :class:`PixPaymentEvent`.

        Returns ``None`` when the body is not a payment event we can act on
        (missing payment object / charge id). Token verification is the
        caller's responsibility and must run first.
        """
        if not isinstance(body, dict):
            return None
        payment = body.get("payment")
        if not isinstance(payment, dict):
            return None
        charge_id = str(payment.get("id") or "")
        if not charge_id:
            return None

        event_type = str(body.get("event") or "")
        # Asaas may omit a top-level event id; fall back to a deterministic
        # composite so the idempotency layer always has a stable key.
        event_id = str(body.get("id") or f"{event_type}:{charge_id}")

        return PixPaymentEvent(
            event_id=event_id,
            event_type=event_type,
            charge_id=charge_id,
            external_reference=str(payment.get("externalReference") or ""),
            amount_centavos=_brl_to_centavos(payment.get("value")),
            status=str(payment.get("status") or ""),
            e2eid=_extract_e2eid(payment),
        )

    # --- internal HTTP helpers -------------------------------------------------

    async def _post(self, client: _AsyncHttpClient, path: str, payload: dict) -> dict:
        try:
            resp = await client.post(
                f"{self._base_url}{path}", headers=self._headers(), json=payload, timeout=self._timeout
            )
            resp.raise_for_status()
            return resp.json()
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 — normalize all transport errors
            logger.warning("asaas_post_failed", path=path, error=str(exc))
            raise ProviderError(f"Asaas POST {path} failed: {exc}") from exc

    async def _get(self, client: _AsyncHttpClient, path: str) -> dict:
        try:
            resp = await client.get(f"{self._base_url}{path}", headers=self._headers(), timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("asaas_get_failed", path=path, error=str(exc))
            raise ProviderError(f"Asaas GET {path} failed: {exc}") from exc

    @staticmethod
    async def _aclose(client: _AsyncHttpClient) -> None:
        close = getattr(client, "aclose", None)
        if close is not None:
            maybe = close()
            if isinstance(maybe, Awaitable):
                await maybe


def _extract_e2eid(payment: dict[str, Any]) -> str | None:
    """Best-effort PIX end-to-end id from the Asaas payment object."""
    pix = payment.get("pixTransaction")
    if isinstance(pix, dict):
        e2e = pix.get("endToEndIdentifier") or pix.get("end2EndId")
        if e2e:
            return str(e2e)
    e2e = payment.get("endToEndIdentifier")
    return str(e2e) if e2e else None
