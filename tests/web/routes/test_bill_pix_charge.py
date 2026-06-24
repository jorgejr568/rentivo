"""Charge-creation wiring tests — POST /billings/.../bills/<uuid>/pix-charge (REN-26).

The Asaas network call is mocked; the test asserts the route persists the PSP
linkage on the bill and surfaces the copy-paste / QR payload.
"""

from __future__ import annotations

import pytest

from rentivo.services.asaas_pix_service import PixCharge, ProviderError
from tests.web.conftest import create_billing_in_db, generate_bill_in_db


@pytest.fixture()
def asaas_enabled(monkeypatch):
    from web import services_container

    monkeypatch.setattr(services_container.settings, "asaas_api_key", "sandbox-key")
    monkeypatch.setattr(services_container.settings, "asaas_webhook_token", "tok")
    yield


def _mock_create_charge(monkeypatch, charge=None, exc=None):
    async def _fake(self, *, external_reference, amount_centavos, customer_id, due_date, description=""):
        if exc is not None:
            raise exc
        return charge or PixCharge(
            charge_id="pay_999",
            external_reference=external_reference,
            copy_paste="00020126_BRCODE",
            qrcode_base64="QkFTRTY0UU4=",
            amount_centavos=amount_centavos,
            status="PENDING",
            expiration="2025-04-10",
        )

    monkeypatch.setattr("rentivo.services.asaas_pix_service.AsaasPixService.create_charge", _fake)


def test_create_pix_charge_persists_and_returns_qr(
    auth_client, asaas_enabled, test_engine, tmp_path, monkeypatch, csrf_token
):
    _mock_create_charge(monkeypatch)
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)

    resp = auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/pix-charge",
        data={"customer_id": "cus_sandbox_1", "csrf_token": csrf_token},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["charge_id"] == "pay_999"
    assert payload["copy_paste"] == "00020126_BRCODE"
    assert payload["qrcode_base64"] == "QkFTRTY0UU4="

    from sqlalchemy import text

    with test_engine.connect() as conn:
        row = conn.execute(
            text("SELECT pix_provider, pix_charge_id FROM bills WHERE uuid = :u"), {"u": bill.uuid}
        ).fetchone()
    assert row[0] == "asaas"
    assert row[1] == "pay_999"


def test_create_pix_charge_requires_customer_id(
    auth_client, asaas_enabled, test_engine, tmp_path, monkeypatch, csrf_token
):
    _mock_create_charge(monkeypatch)
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)

    resp = auth_client.post(f"/billings/{billing.uuid}/bills/{bill.uuid}/pix-charge", data={"csrf_token": csrf_token})
    assert resp.status_code == 400
    assert resp.json()["error"] == "customer_id_required"


def test_create_pix_charge_disabled_returns_503(auth_client, test_engine, tmp_path, csrf_token):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    resp = auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/pix-charge", data={"customer_id": "x", "csrf_token": csrf_token}
    )
    assert resp.status_code == 503


def test_create_pix_charge_provider_error_returns_502(
    auth_client, asaas_enabled, test_engine, tmp_path, monkeypatch, csrf_token
):
    _mock_create_charge(monkeypatch, exc=ProviderError("boom"))
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)

    resp = auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/pix-charge",
        data={"customer_id": "cus_1", "csrf_token": csrf_token},
    )
    assert resp.status_code == 502
    assert resp.json()["error"] == "provider_error"
