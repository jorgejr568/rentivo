"""Unit tests for the Asaas dynamic-PIX provider client (REN-15)."""

from unittest.mock import AsyncMock

import pytest

from rentivo.services.asaas_pix_service import (
    AsaasPixService,
    PixPaymentEvent,
    ProviderError,
    _brl_to_centavos,
    _centavos_to_brl,
)


def _json_response(payload: dict):
    resp = AsyncMock()
    resp.json = lambda: payload
    resp.raise_for_status = lambda: None
    return resp


def _service(client=None, **kwargs):
    defaults = dict(api_key="sandbox-key", webhook_token="hook-secret")
    defaults.update(kwargs)
    if client is not None:
        defaults["http_client_factory"] = lambda: client
    return AsaasPixService(**defaults)


# --- enablement / config ------------------------------------------------------


def test_disabled_without_api_key():
    assert _service(api_key="").is_enabled is False
    assert _service(api_key="k").is_enabled is True


def test_provider_name():
    assert _service().provider_name == "asaas"


@pytest.mark.asyncio
async def test_create_charge_raises_when_disabled():
    svc = _service(api_key="")
    with pytest.raises(ProviderError):
        await svc.create_charge(
            external_reference="bill-uuid", amount_centavos=150000, customer_id="cus_1", due_date="2026-07-01"
        )


# --- charge creation ----------------------------------------------------------


@pytest.mark.asyncio
async def test_create_charge_posts_payment_then_fetches_qr():
    client = AsyncMock()
    client.post = AsyncMock(return_value=_json_response({"id": "pay_123", "status": "PENDING"}))
    client.get = AsyncMock(
        return_value=_json_response(
            {"payload": "00020126...br.gov.bcb.pix", "encodedImage": "QUJD", "expirationDate": "2026-07-01 23:59:59"}
        )
    )
    svc = _service(client)

    charge = await svc.create_charge(
        external_reference="bill-uuid-1", amount_centavos=150000, customer_id="cus_9", due_date="2026-07-01"
    )

    assert charge.charge_id == "pay_123"
    assert charge.external_reference == "bill-uuid-1"
    assert charge.copy_paste.startswith("00020126")
    assert charge.qrcode_base64 == "QUJD"
    assert charge.amount_centavos == 150000

    # Payment POST: PIX billing type, value in BRL, externalReference carried.
    post_args, post_kwargs = client.post.call_args
    assert post_args[0].endswith("/payments")
    assert post_kwargs["headers"]["access_token"] == "sandbox-key"
    body = post_kwargs["json"]
    assert body["billingType"] == "PIX"
    assert body["value"] == 1500.00
    assert body["externalReference"] == "bill-uuid-1"
    assert body["customer"] == "cus_9"

    # QR fetched for the returned payment id.
    get_args, _ = client.get.call_args
    assert get_args[0].endswith("/payments/pay_123/pixQrCode")


@pytest.mark.asyncio
async def test_create_charge_missing_payment_id_raises():
    client = AsyncMock()
    client.post = AsyncMock(return_value=_json_response({"status": "PENDING"}))
    svc = _service(client)
    with pytest.raises(ProviderError):
        await svc.create_charge(external_reference="b", amount_centavos=1000, customer_id="c", due_date="2026-07-01")


@pytest.mark.asyncio
async def test_create_charge_wraps_transport_errors():
    client = AsyncMock()
    client.post = AsyncMock(side_effect=RuntimeError("network down"))
    svc = _service(client)
    with pytest.raises(ProviderError):
        await svc.create_charge(external_reference="b", amount_centavos=1000, customer_id="c", due_date="2026-07-01")


# --- webhook authentication ---------------------------------------------------


def test_verify_webhook_token_accepts_matching_secret():
    assert _service().verify_webhook_token("hook-secret") is True


def test_verify_webhook_token_rejects_wrong_secret():
    assert _service().verify_webhook_token("nope") is False


def test_verify_webhook_token_rejects_missing_token():
    assert _service().verify_webhook_token(None) is False
    assert _service().verify_webhook_token("") is False


def test_verify_webhook_token_fails_closed_when_unconfigured():
    """No configured secret => reject everything (never accept an unauthenticated webhook)."""
    assert _service(webhook_token="").verify_webhook_token("anything") is False


# --- webhook parsing ----------------------------------------------------------


def test_parse_webhook_normalizes_payment_received():
    body = {
        "id": "evt_555",
        "event": "PAYMENT_RECEIVED",
        "payment": {
            "id": "pay_123",
            "externalReference": "bill-uuid-1",
            "value": 1500.00,
            "status": "RECEIVED",
            "pixTransaction": {"endToEndIdentifier": "E1234"},
        },
    }
    event = _service().parse_webhook(body)
    assert isinstance(event, PixPaymentEvent)
    assert event.event_id == "evt_555"
    assert event.event_type == "PAYMENT_RECEIVED"
    assert event.charge_id == "pay_123"
    assert event.external_reference == "bill-uuid-1"
    assert event.amount_centavos == 150000
    assert event.e2eid == "E1234"
    assert event.is_paid is True


def test_parse_webhook_non_paid_event_is_not_paid():
    body = {"id": "evt_1", "event": "PAYMENT_CREATED", "payment": {"id": "pay_1", "value": 10.0}}
    event = _service().parse_webhook(body)
    assert event is not None
    assert event.is_paid is False


def test_parse_webhook_falls_back_to_composite_event_id():
    body = {"event": "PAYMENT_CONFIRMED", "payment": {"id": "pay_9", "value": 10.0}}
    event = _service().parse_webhook(body)
    assert event.event_id == "PAYMENT_CONFIRMED:pay_9"


def test_parse_webhook_returns_none_without_payment():
    assert _service().parse_webhook({"event": "PAYMENT_RECEIVED"}) is None
    assert _service().parse_webhook({"payment": {}}) is None
    assert _service().parse_webhook({"payment": {"id": ""}}) is None


# --- currency helpers ---------------------------------------------------------


@pytest.mark.parametrize("centavos,brl", [(0, 0.0), (1, 0.01), (150000, 1500.0), (199, 1.99)])
def test_centavos_to_brl(centavos, brl):
    assert _centavos_to_brl(centavos) == brl


def test_centavos_to_brl_rejects_negative():
    with pytest.raises(ValueError):
        _centavos_to_brl(-1)


@pytest.mark.parametrize("value,centavos", [(1500.00, 150000), (1.99, 199), ("1500.00", 150000), (None, 0), ("x", 0)])
def test_brl_to_centavos(value, centavos):
    assert _brl_to_centavos(value) == centavos
