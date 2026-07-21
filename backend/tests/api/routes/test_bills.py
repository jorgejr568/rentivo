from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from rentivo.analytics import analytics_hash
from rentivo.api.app import create_app
from rentivo.api.authentication import get_principal
from rentivo.api.dependencies import get_services
from rentivo.api.principal import Principal
from rentivo.constants.api_scopes import APIScope
from rentivo.models.api_key import APIKey, APIKeyGrant
from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import Bill, BillLineItem, InvalidStatusTransition
from rentivo.models.billing import Billing, BillingItem, ItemType
from rentivo.models.communication import Communication
from rentivo.models.receipt import MAX_RECEIPT_SIZE, Receipt
from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyReceiptRepository,
)
from rentivo.services.bill_service import BillService, StaleReceiptDeleteError
from rentivo.services.job_service import JobService
from rentivo.storage.base import FileRef
from rentivo.storage.local import LocalStorage

NOW = datetime(2026, 7, 18, 12, tzinfo=UTC)
USER = User(id=7, email="bills@example.com")
BILLING = Billing(
    id=31,
    uuid="01JBILLING00000000000000000",
    name="Apartamento 101",
    owner_type="user",
    owner_id=USER.id,
    items=[
        BillingItem(
            id=101,
            uuid="01J00000000000000000000010",
            description="Aluguel",
            amount=285_000,
            item_type=ItemType.FIXED,
            sort_order=0,
        ),
        BillingItem(
            id=102,
            uuid="01J00000000000000000000011",
            description="Agua",
            amount=0,
            item_type=ItemType.VARIABLE,
            sort_order=1,
        ),
    ],
)
OTHER_BILLING = BILLING.model_copy(update={"id": 32, "uuid": "01JOTHERBILLING000000000000", "name": "Apartamento 202"})
BILL = Bill(
    id=41,
    uuid="01JBILL00000000000000000000",
    billing_id=BILLING.id,
    reference_month="2026-07",
    total_amount=292_500,
    line_items=[
        BillLineItem(description="Aluguel", amount=285_000, item_type=ItemType.FIXED, sort_order=0),
        BillLineItem(description="Agua", amount=7_500, item_type=ItemType.VARIABLE, sort_order=1),
    ],
    pdf_path="private/invoice.pdf",
    notes="Sem multa",
    due_date="2026-08-10",
    status="draft",
    pdf_render_status="succeeded",
    created_at=NOW,
)
OTHER_BILL = BILL.model_copy(update={"id": 42, "uuid": "01JOTHERBILL000000000000000", "billing_id": OTHER_BILLING.id})
RECEIPT = Receipt(
    id=51,
    uuid="01J00000000000000000000000",
    bill_id=BILL.id,
    filename="comprovante.pdf",
    storage_key="private/receipt.pdf",
    content_type="application/pdf",
    file_size=1234,
    sort_order=0,
    created_at=NOW,
)
OTHER_RECEIPT = RECEIPT.model_copy(update={"id": 52, "uuid": "01J00000000000000000000001", "bill_id": OTHER_BILL.id})
COMMUNICATION = Communication(
    id=61,
    uuid="01JCOMM00000000000000000000",
    bill_id=BILL.id,
    comm_type="bill_ready",
    recipient_name="Maria",
    recipient_email="maria@example.com",
    subject="Fatura de julho",
    body_markdown="Ola",
    status="sent",
    created_at=NOW,
    sent_at=NOW,
)

ALL_SCOPES = frozenset(scope.value for scope in APIScope)
BEARER_HEADERS = {"Authorization": "Bearer test-secret"}


class _AlwaysFailJobBackend:
    def __init__(self) -> None:
        self.queued: list[object] = []

    def enqueue(self, job_type, payload, run_after=None, max_attempts=5):
        raise RuntimeError("job backend failed")


def _api_key(*, scopes: frozenset[str] = ALL_SCOPES, is_login_token: bool = False) -> APIKey:
    return APIKey(
        id=1,
        uuid="01JKEY000000000000000000000",
        user_id=USER.id,
        name="Test key",
        secret_hash=b"x" * 32,
        key_start="test",
        key_end="key",
        is_login_token=is_login_token,
        scopes=scopes,
        grants=(APIKeyGrant(resource_type="user", resource_id=USER.id),),
        expires_at=NOW + timedelta(days=1),
    )


def _principal(*, scopes: frozenset[str] = ALL_SCOPES, is_login_token: bool = False) -> Principal:
    return Principal(
        user=USER,
        api_key=_api_key(scopes=scopes, is_login_token=is_login_token),
        source="web" if is_login_token else "integration",
    )


def _updated_bill(bill: Bill, **changes: object) -> Bill:
    return bill.model_copy(update=changes)


def _services(state: SimpleNamespace) -> SimpleNamespace:
    billing_service = MagicMock()
    billing_service.get_billing_by_uuid.side_effect = lambda uuid: {
        BILLING.uuid: BILLING,
        OTHER_BILLING.uuid: OTHER_BILLING,
    }.get(uuid)

    bill_service = MagicMock()
    bill_service.get_bill_by_uuid.side_effect = lambda uuid: {
        BILL.uuid: BILL,
        OTHER_BILL.uuid: OTHER_BILL,
    }.get(uuid)
    bill_service.list_bills.return_value = [BILL]
    bill_service.list_receipts.return_value = [RECEIPT]
    bill_service.get_receipt_by_uuid.side_effect = lambda uuid: {
        RECEIPT.uuid: RECEIPT,
        OTHER_RECEIPT.uuid: OTHER_RECEIPT,
    }.get(uuid)
    bill_service.get_invoice_ref.return_value = FileRef(kind="url", location="https://files.example/invoice.pdf")
    bill_service.get_recibo_ref.return_value = FileRef(kind="url", location="https://files.example/recibo.pdf")
    bill_service.get_receipt_ref.return_value = FileRef(kind="url", location="https://files.example/receipt.pdf")
    bill_service.render_recibo.return_value = b"%PDF-recibo"

    created_bill = _updated_bill(
        BILL,
        id=43,
        uuid="01JCREATEDBILL0000000000000",
        line_items=[
            BillLineItem(description="Aluguel", amount=285_000, item_type=ItemType.FIXED, sort_order=0),
            BillLineItem(description="Agua", amount=8_000, item_type=ItemType.VARIABLE, sort_order=1),
            BillLineItem(description="Chaveiro", amount=5_000, item_type=ItemType.EXTRA, sort_order=2),
        ],
        total_amount=298_000,
        due_date="2026-08-10",
        pdf_path=None,
        pdf_render_status="pending",
    )
    bill_service.generate_bill.return_value = created_bill

    def update_bill(*, bill: Bill, line_items: list[BillLineItem], notes: str, due_date: str, **_kwargs):
        return _updated_bill(
            bill,
            line_items=line_items,
            total_amount=sum(item.amount for item in line_items),
            notes=notes,
            due_date=due_date or None,
            pdf_render_status="pending",
        )

    bill_service.update_bill.side_effect = update_bill

    def change_status(bill: Bill, target: str, **_kwargs):
        return _updated_bill(bill, status=target, status_updated_at=NOW)

    bill_service.change_status.side_effect = change_status

    upload_index = 0

    def add_receipt(*, bill: Bill, filename: str, file_bytes: bytes, content_type: str, **_kwargs):
        nonlocal upload_index
        upload_index += 1
        return (
            Receipt(
                id=70 + upload_index,
                uuid=f"01JUPLOADED{upload_index:02d}00000000000000",
                bill_id=bill.id,
                filename=filename,
                storage_key=f"private/upload-{upload_index}",
                content_type=content_type,
                file_size=len(file_bytes),
                sort_order=upload_index - 1,
                created_at=NOW,
            ),
            [],
        )

    bill_service.add_receipt.side_effect = add_receipt

    authorization = MagicMock()
    authorization.get_role_for_billing.side_effect = lambda _user_id, _billing: state.role
    pix = MagicMock()
    pix.billing_needs_setup.side_effect = lambda _billing: state.pix_missing
    api_key = MagicMock()
    api_key.can_access_resource.side_effect = lambda *_args: state.granted

    communication = MagicMock()
    communication.list_for_bill.return_value = [COMMUNICATION]

    return SimpleNamespace(
        billing=billing_service,
        bill=bill_service,
        authorization=authorization,
        pix=pix,
        api_key=api_key,
        communication=communication,
        audit=MagicMock(),
        storage_cleanup=MagicMock(),
    )


@dataclass
class BillsAPI:
    client: TestClient
    state: SimpleNamespace
    services: SimpleNamespace

    def set_scopes(self, *scopes: APIScope) -> None:
        self.state.principal = _principal(scopes=frozenset(scope.value for scope in scopes))

    def set_login_principal(self) -> None:
        self.state.principal = _principal(is_login_token=True)


@pytest.fixture
def api() -> BillsAPI:
    state = SimpleNamespace(
        role="owner",
        granted=True,
        pix_missing=False,
        principal=_principal(),
    )
    services = _services(state)
    app = create_app()

    try:
        bills_router = import_module("rentivo.api.routes.bills").router
    except ModuleNotFoundError:
        bills_router = None
    if bills_router is not None:
        app.include_router(bills_router, prefix="/api/v1")

    @app.middleware("http")
    async def set_auth_transport(request: Request, call_next):
        request.state.auth_transport = "bearer" if request.headers.get("Authorization") else "cookie"
        return await call_next(request)

    app.dependency_overrides[get_services] = lambda: services
    app.dependency_overrides[get_principal] = lambda: state.principal
    client = TestClient(app)
    yield BillsAPI(client=client, state=state, services=services)
    client.close()


def _detail_url(bill: Bill = BILL, billing: Billing = BILLING) -> str:
    return f"/api/v1/billings/{billing.uuid}/bills/{bill.uuid}"


def _create_payload() -> dict[str, object]:
    return {
        "reference_month": "2026-08",
        "due_date": "2026-08-10",
        "notes": "Pagar ate o vencimento",
        "variable_amounts": {"01J00000000000000000000011": 8_000},
        "extras": [{"description": " Chaveiro ", "amount": 5_000}],
    }


def _analytics_headers(response) -> dict[str, str]:
    return {
        name.lower(): value
        for name, value in response.headers.items()
        if name.lower().startswith("x-rentivo-analytics-")
    }


def test_receipt_multipart_openapi_exposes_browser_blob_types() -> None:
    openapi = create_app().openapi()
    schema = openapi["components"]["schemas"]

    create_files = schema["Body_create_bill_api_v1_billings__billing_uuid__bills_post"]["properties"]["receipt_files"]
    upload_files = schema["Body_upload_receipts_api_v1_billings__billing_uuid__bills__bill_uuid__receipts_post"][
        "properties"
    ]["receipt_files"]

    assert create_files["anyOf"][0]["items"] == {"type": "string", "format": "binary"}
    assert upload_files["items"] == {"type": "string", "format": "binary"}

    create_body = openapi["paths"]["/api/v1/billings/{billing_uuid}/bills"]["post"]["requestBody"]
    assert set(create_body["content"]) == {"application/json", "multipart/form-data"}
    assert create_body["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/BillCreateRequest"}
    multipart = create_body["content"]["multipart/form-data"]
    assert "$ref" not in multipart["schema"]
    assert multipart["schema"]["properties"]["payload"] == {"$ref": "#/components/schemas/BillCreateRequest"}
    assert multipart["schema"]["properties"]["receipt_files"]["items"] == {
        "type": "string",
        "format": "binary",
    }
    assert multipart["encoding"]["payload"] == {"contentType": "application/json"}
    assert schema["BillCreateRequest"]["properties"]["reference_month"]["type"] == "string"


def test_recibo_download_handshake_openapi_uses_named_response_schema() -> None:
    openapi = create_app().openapi()
    operation = openapi["paths"]["/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/recibo/download"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ReciboDownloadResponse"
    }
    schema = openapi["components"]["schemas"]["ReciboDownloadResponse"]
    assert schema["required"] == ["download_url", "filename"]
    assert schema["properties"]["download_url"]["format"] == "uri"


def test_list_bills_returns_public_invoice_data_without_storage_paths(api: BillsAPI) -> None:
    response = api.client.get(f"/api/v1/billings/{BILLING.uuid}/bills", headers=BEARER_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["uuid"] == BILL.uuid
    assert body["items"][0]["total_amount"] == 292_500
    assert body["items"][0]["has_invoice"] is True
    assert "pdf_path" not in response.text
    assert "recibo_pdf_path" not in response.text
    api.services.bill.list_bills.assert_called_once_with(BILLING.id)


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("10/08/2026", "2026-08-10"),
        ("2026-08-10", "2026-08-10"),
        (None, None),
        ("nao informado", None),
    ],
)
def test_due_date_is_normalized_to_iso_8601_or_null(
    api: BillsAPI,
    stored: str | None,
    expected: str | None,
) -> None:
    legacy_bill = BILL.model_copy(update={"due_date": stored})
    api.services.bill.list_bills.return_value = [legacy_bill]

    response = api.client.get(f"/api/v1/billings/{BILLING.uuid}/bills", headers=BEARER_HEADERS)

    assert response.status_code == 200
    assert response.json()["items"][0]["due_date"] == expected


def test_bill_reads_require_scope_grant_and_parent_child_linkage(api: BillsAPI) -> None:
    api.set_scopes(APIScope.FILES_READ)
    missing_scope = api.client.get(_detail_url(), headers=BEARER_HEADERS)
    assert missing_scope.status_code == 403
    assert missing_scope.json()["code"] == "missing_scope"

    api.set_scopes(APIScope.BILLS_READ)
    api.state.granted = False
    outside_grant = api.client.get(_detail_url(), headers=BEARER_HEADERS)
    assert outside_grant.status_code == 404

    api.state.granted = True
    mismatch = api.client.get(_detail_url(OTHER_BILL, BILLING), headers=BEARER_HEADERS)
    assert mismatch.status_code == 404


def test_bill_detail_redacts_complete_communication_payload_for_integration_keys(api: BillsAPI) -> None:
    response = api.client.get(_detail_url(), headers=BEARER_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert {transition["target"] for transition in body["available_transitions"]} == {
        "published",
        "sent",
        "cancelled",
    }
    cancel = next(item for item in body["available_transitions"] if item["target"] == "cancelled")
    assert cancel == {
        "target": "cancelled",
        "label": "Cancelar fatura",
        "style": "danger",
        "requires_confirmation": True,
    }
    assert body["capabilities"]["can_delete"] is True
    assert body["capabilities"]["can_compose"] is True
    assert body["capabilities"]["can_send_invoice"] is True
    assert body["capabilities"]["can_send_recibo"] is False
    assert body["receipts"][0]["content_type"] == "application/pdf"
    assert body["communications"] == [
        {
            "uuid": COMMUNICATION.uuid,
            "comm_type": "bill_ready",
            "status": "sent",
            "created_at": NOW.isoformat().replace("+00:00", "Z"),
            "sent_at": NOW.isoformat().replace("+00:00", "Z"),
        }
    ]
    assert COMMUNICATION.recipient_name not in response.text
    assert COMMUNICATION.recipient_email not in response.text
    assert COMMUNICATION.subject not in response.text
    assert "storage_key" not in response.text


def test_bill_detail_returns_communication_pii_only_to_login_tokens(api: BillsAPI) -> None:
    api.set_login_principal()

    response = api.client.get(_detail_url())

    assert response.status_code == 200
    assert response.json()["communications"][0] == {
        "uuid": COMMUNICATION.uuid,
        "comm_type": "bill_ready",
        "recipient_name": COMMUNICATION.recipient_name,
        "recipient_email": COMMUNICATION.recipient_email,
        "subject": COMMUNICATION.subject,
        "status": "sent",
        "created_at": NOW.isoformat().replace("+00:00", "Z"),
        "sent_at": NOW.isoformat().replace("+00:00", "Z"),
    }


def test_detail_omits_scoped_children_and_mutation_capabilities_without_their_scopes(api: BillsAPI) -> None:
    api.set_scopes(APIScope.BILLS_READ)

    response = api.client.get(_detail_url(), headers=BEARER_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["receipts"] == []
    assert body["communications"] == []
    assert body["available_transitions"] == []
    assert not any(body["capabilities"].values())


def test_viewer_has_read_only_capabilities_even_with_every_scope(api: BillsAPI) -> None:
    api.state.role = "viewer"

    response = api.client.get(_detail_url(), headers=BEARER_HEADERS)

    assert response.status_code == 200
    assert response.json()["available_transitions"] == []
    assert response.json()["capabilities"] == {
        "can_edit": False,
        "can_delete": False,
        "can_transition": False,
        "can_regenerate": False,
        "can_upload_receipts": False,
        "can_delete_receipts": False,
        "can_reorder_receipts": False,
        "can_download_invoice": True,
        "can_download_recibo": False,
        "can_compose": False,
        "can_send_invoice": False,
        "can_send_recibo": False,
    }


def test_communication_capabilities_require_both_scopes_and_ready_artifacts(api: BillsAPI) -> None:
    api.set_scopes(APIScope.BILLS_READ, APIScope.COMMUNICATIONS_READ)
    missing_send = api.client.get(_detail_url(), headers=BEARER_HEADERS)
    assert missing_send.status_code == 200
    assert (
        missing_send.json()["capabilities"]
        | {
            "can_compose": False,
            "can_send_invoice": False,
            "can_send_recibo": False,
        }
        == missing_send.json()["capabilities"]
    )

    api.set_scopes(APIScope.BILLS_READ, APIScope.FILES_READ, APIScope.COMMUNICATIONS_READ, APIScope.COMMUNICATIONS_SEND)
    rendering = BILL.model_copy(update={"status": "paid", "recibo_pdf_path": None, "pdf_render_status": "pending"})
    ready = rendering.model_copy(update={"recibo_pdf_path": "private/recibo.pdf", "pdf_render_status": "succeeded"})
    api.services.bill.get_bill_by_uuid.side_effect = lambda _uuid: rendering
    pending_response = api.client.get(_detail_url(), headers=BEARER_HEADERS)
    api.services.bill.get_bill_by_uuid.side_effect = lambda _uuid: ready
    ready_response = api.client.get(_detail_url(), headers=BEARER_HEADERS)

    assert pending_response.json()["capabilities"]["can_compose"] is True
    assert pending_response.json()["capabilities"]["can_send_invoice"] is True
    assert pending_response.json()["capabilities"]["can_download_recibo"] is False
    assert pending_response.json()["capabilities"]["can_send_recibo"] is False
    assert ready_response.json()["capabilities"]["can_download_recibo"] is True
    assert ready_response.json()["capabilities"]["can_send_recibo"] is True


def test_create_bill_accepts_integer_centavos_and_renders_once(api: BillsAPI) -> None:
    response = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        json=_create_payload(),
        headers=BEARER_HEADERS,
    )

    assert response.status_code == 201
    call = api.services.bill.generate_bill.call_args
    assert call.kwargs["reference_month"] == "2026-08"
    assert call.kwargs["variable_amounts"] == {"01J00000000000000000000011": 8_000}
    assert call.kwargs["extras"] == [("Chaveiro", 5_000)]
    assert call.kwargs["due_date"] == "10/08/2026"
    assert call.kwargs["render"] is False
    api.services.bill.regenerate_pdf.assert_called_once_with(
        api.services.bill.generate_bill.return_value,
        BILLING,
        actor=api.state.principal.actor,
    )
    assert api.services.audit.safe_log_for.call_args_list[0].args[1] == AuditEventType.BILL_CREATE
    bill = api.services.bill.generate_bill.return_value
    assert _analytics_headers(response) == {
        "x-rentivo-analytics-event": "rentivo_bill_generated",
        "x-rentivo-analytics-billing-uuid-hash": analytics_hash(BILLING.uuid),
        "x-rentivo-analytics-bill-uuid-hash": analytics_hash(bill.uuid),
        "x-rentivo-analytics-reference-month": bill.reference_month,
        "x-rentivo-analytics-line-item-count": str(len(bill.line_items)),
        "x-rentivo-analytics-total-amount-brl": str(round(bill.total_amount / 100)),
        "x-rentivo-analytics-receipt-count": "0",
    }


def test_create_bill_rejects_duplicate_variable_uuid_keys_before_generation(api: BillsAPI) -> None:
    response = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        content=(
            '{"reference_month":"2026-08","variable_amounts":{'
            '"01J00000000000000000000011":8000,'
            '"01J00000000000000000000011":9000}}'
        ),
        headers={**BEARER_HEADERS, "Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["fields"] == {"variable_amounts": "Cada item variável deve aparecer uma única vez."}
    api.services.bill.generate_bill.assert_not_called()


def test_create_bill_requires_every_variable_uuid_before_generation(api: BillsAPI) -> None:
    payload = _create_payload()
    payload["variable_amounts"] = {}

    response = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        json=payload,
        headers=BEARER_HEADERS,
    )

    assert response.status_code == 422
    assert response.json()["fields"] == {
        "variable_amounts": "Informe o valor de todos os itens variáveis.",
    }
    api.services.bill.generate_bill.assert_not_called()


def test_create_bill_with_receipts_audits_create_first_and_still_renders_once(api: BillsAPI) -> None:
    response = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        data={"payload": json.dumps(_create_payload())},
        files=[
            ("receipt_files", ("a.pdf", b"%PDF-a", "application/pdf")),
            ("receipt_files", ("b.png", b"png-data", "image/png")),
            ("receipt_files", ("bad.gif", b"gif-data", "image/gif")),
        ],
        headers=BEARER_HEADERS,
    )

    assert response.status_code == 201
    assert response.json()["receipt_upload"] == {"attached": 2, "skipped": 1, "total_bytes": 14}
    assert api.services.bill.add_receipt.call_count == 2
    assert all(call.kwargs["render"] is False for call in api.services.bill.add_receipt.call_args_list)
    api.services.bill.regenerate_pdf.assert_called_once()
    events = [call.args[1] for call in api.services.audit.safe_log_for.call_args_list]
    assert events == [
        AuditEventType.BILL_CREATE,
        AuditEventType.RECEIPT_UPLOAD,
        AuditEventType.RECEIPT_UPLOAD,
    ]


def test_create_bill_rolls_back_bill_and_partial_receipts_when_later_upload_fails(api: BillsAPI) -> None:
    first_receipt = RECEIPT.model_copy(update={"id": 71, "bill_id": 43})
    api.services.bill.add_receipt.side_effect = [(first_receipt, []), RuntimeError("second upload failed")]

    with pytest.raises(RuntimeError, match="second upload failed"):
        api.client.post(
            f"/api/v1/billings/{BILLING.uuid}/bills",
            data={"payload": json.dumps(_create_payload())},
            files=[
                ("receipt_files", ("a.pdf", b"%PDF-a", "application/pdf")),
                ("receipt_files", ("b.pdf", b"%PDF-b", "application/pdf")),
            ],
            headers=BEARER_HEADERS,
        )

    api.services.bill.rollback_receipt_batch.assert_called_once_with((first_receipt,))
    api.services.bill.rollback_bill_creation.assert_called_once_with(
        api.services.bill.generate_bill.return_value,
        BILLING,
    )
    api.services.bill.regenerate_pdf.assert_not_called()
    api.services.audit.safe_log_for.assert_not_called()


def test_create_bill_rolls_back_bill_and_receipts_when_render_scheduling_fails(api: BillsAPI) -> None:
    attached = RECEIPT.model_copy(update={"id": 71, "bill_id": 43})
    api.services.bill.add_receipt.side_effect = [(attached, [])]
    api.services.bill.regenerate_pdf.side_effect = RuntimeError("render enqueue failed")

    with pytest.raises(RuntimeError, match="render enqueue failed"):
        api.client.post(
            f"/api/v1/billings/{BILLING.uuid}/bills",
            data={"payload": json.dumps(_create_payload())},
            files=[("receipt_files", ("a.pdf", b"%PDF-a", "application/pdf"))],
            headers=BEARER_HEADERS,
        )

    api.services.bill.rollback_bill_creation.assert_called_once_with(
        api.services.bill.generate_bill.return_value,
        BILLING,
    )
    api.services.audit.safe_log_for.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {**_create_payload(), "reference_month": "2026-13"},
        {**_create_payload(), "due_date": "10/08/2026"},
        {**_create_payload(), "extras": [{"description": " ", "amount": 100}]},
        {**_create_payload(), "extras": [{"description": "Taxa", "amount": 0}]},
        {**_create_payload(), "unexpected": True},
    ],
)
def test_create_bill_rejects_invalid_strict_payloads(api: BillsAPI, payload: dict[str, object]) -> None:
    response = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        json=payload,
        headers=BEARER_HEADERS,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    api.services.bill.generate_bill.assert_not_called()


def test_create_bill_rejects_malformed_json(api: BillsAPI) -> None:
    response = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        content=b"{",
        headers={**BEARER_HEADERS, "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["fields"] == {}


def test_create_bill_maps_domain_variable_amount_rejection(api: BillsAPI) -> None:
    api.services.bill.generate_bill.side_effect = ValueError("Item variável desconhecido")

    response = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        json=_create_payload(),
        headers=BEARER_HEADERS,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_variable_amounts"
    assert response.json()["fields"] == {"variable_amounts": "Item variável desconhecido"}


def test_create_resolves_access_before_parsing_body(api: BillsAPI) -> None:
    api.state.granted = False
    response = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        content=b"{",
        headers={**BEARER_HEADERS, "Content-Type": "application/json"},
    )
    assert response.status_code == 404


@pytest.mark.parametrize("role", ["owner", "admin", "manager"])
def test_bill_managers_can_create(api: BillsAPI, role: str) -> None:
    api.state.role = role
    response = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        json=_create_payload(),
        headers=BEARER_HEADERS,
    )
    assert response.status_code == 201


def test_create_requires_manage_role_and_complete_pix(api: BillsAPI) -> None:
    api.state.role = "viewer"
    denied = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        json=_create_payload(),
        headers=BEARER_HEADERS,
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "insufficient_role"

    api.state.role = "manager"
    api.state.pix_missing = True
    pix = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        json=_create_payload(),
        headers=BEARER_HEADERS,
    )
    assert pix.status_code == 409
    assert pix.json()["code"] == "pix_setup_required"


def test_create_requires_file_write_scope_only_when_receipts_are_included(api: BillsAPI) -> None:
    api.set_scopes(APIScope.BILLS_WRITE)
    without_receipts = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        json=_create_payload(),
        headers=BEARER_HEADERS,
    )
    assert without_receipts.status_code == 201

    api.services.bill.reset_mock()
    with_receipt = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        data={"payload": json.dumps(_create_payload())},
        files=[("receipt_files", ("a.pdf", b"%PDF-a", "application/pdf"))],
        headers=BEARER_HEADERS,
    )
    assert with_receipt.status_code == 403
    assert with_receipt.json()["code"] == "missing_scope"
    api.services.bill.generate_bill.assert_not_called()


def test_browser_mutations_require_csrf_but_bearer_mutations_do_not(api: BillsAPI) -> None:
    api.set_login_principal()
    without_csrf = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        json=_create_payload(),
    )
    assert without_csrf.status_code == 403
    assert without_csrf.json()["code"] == "csrf_failed"

    api.state.principal = _principal()
    bearer = api.client.post(
        f"/api/v1/billings/{BILLING.uuid}/bills",
        json=_create_payload(),
        headers=BEARER_HEADERS,
    )
    assert bearer.status_code == 201


def test_patch_bill_preserves_omitted_values_and_audits(api: BillsAPI) -> None:
    response = api.client.patch(
        _detail_url(),
        json={"notes": "Atualizada"},
        headers=BEARER_HEADERS,
    )

    assert response.status_code == 200
    call = api.services.bill.update_bill.call_args
    assert call.kwargs["line_items"] == BILL.line_items
    assert call.kwargs["notes"] == "Atualizada"
    assert call.kwargs["due_date"] == BILL.due_date
    assert call.kwargs["actor"] == api.state.principal.actor
    audit = api.services.audit.safe_log_for.call_args
    assert audit.args[1] == AuditEventType.BILL_UPDATE
    assert audit.kwargs["previous_state"]["notes"] == BILL.notes
    assert audit.kwargs["new_state"]["notes"] == "Atualizada"
    assert _analytics_headers(response) == {
        "x-rentivo-analytics-event": "rentivo_bill_edited",
        "x-rentivo-analytics-bill-uuid-hash": analytics_hash(BILL.uuid),
    }


def test_patch_bill_replaces_line_items_and_can_clear_due_date(api: BillsAPI) -> None:
    response = api.client.patch(
        _detail_url(),
        json={
            "line_items": [
                {"description": " Aluguel atualizado ", "amount": 300_000, "item_type": "fixed"},
                {"description": "Extra", "amount": 1_000, "item_type": "extra"},
            ],
            "due_date": None,
        },
        headers=BEARER_HEADERS,
    )

    assert response.status_code == 200
    call = api.services.bill.update_bill.call_args
    assert [(item.description, item.amount, item.sort_order) for item in call.kwargs["line_items"]] == [
        ("Aluguel atualizado", 300_000, 0),
        ("Extra", 1_000, 1),
    ]
    assert call.kwargs["due_date"] == ""


def test_patch_converts_iso_due_date_for_domain_storage_and_pdf(api: BillsAPI) -> None:
    response = api.client.patch(
        _detail_url(),
        json={"due_date": "2026-12-31"},
        headers=BEARER_HEADERS,
    )
    assert response.status_code == 200
    assert api.services.bill.update_bill.call_args.kwargs["due_date"] == "31/12/2026"


@pytest.mark.parametrize(
    "payload",
    [{}, {"due_date": "31/12/2026"}, {"line_items": [{"description": " ", "amount": 1, "item_type": "fixed"}]}],
)
def test_patch_rejects_empty_or_invalid_payload(api: BillsAPI, payload: dict[str, object]) -> None:
    response = api.client.patch(_detail_url(), json=payload, headers=BEARER_HEADERS)
    assert response.status_code == 422


def test_patch_requires_manage_role_pix_and_write_scope(api: BillsAPI) -> None:
    api.set_scopes(APIScope.BILLS_READ)
    missing_scope = api.client.patch(_detail_url(), json={"notes": "x"}, headers=BEARER_HEADERS)
    assert missing_scope.status_code == 403

    api.set_scopes(APIScope.BILLS_WRITE)
    api.state.role = "viewer"
    role = api.client.patch(_detail_url(), json={"notes": "x"}, headers=BEARER_HEADERS)
    assert role.status_code == 403

    api.state.role = "manager"
    api.state.pix_missing = True
    pix = api.client.patch(_detail_url(), json={"notes": "x"}, headers=BEARER_HEADERS)
    assert pix.status_code == 409


def test_allowed_transition_uses_policy_and_audits_status_change(api: BillsAPI) -> None:
    response = api.client.post(
        f"{_detail_url()}/transitions",
        json={"target": "published", "current_status": "draft"},
        headers=BEARER_HEADERS,
    )

    assert response.status_code == 200
    api.services.bill.change_status.assert_called_once_with(
        BILL,
        "published",
        billing=BILLING,
        actor=api.state.principal.actor,
    )
    audit = api.services.audit.safe_log_for.call_args
    assert audit.args[1] == AuditEventType.BILL_STATUS_CHANGE
    assert audit.kwargs["previous_state"] == {"status": "draft"}
    assert audit.kwargs["new_state"] == {"status": "published"}
    assert _analytics_headers(response) == {
        "x-rentivo-analytics-event": "rentivo_bill_status_changed",
        "x-rentivo-analytics-bill-uuid-hash": analytics_hash(BILL.uuid),
        "x-rentivo-analytics-new-status": "published",
    }


def test_transition_rejects_stale_disallowed_unknown_and_viewer_requests(api: BillsAPI) -> None:
    stale = api.client.post(
        f"{_detail_url()}/transitions",
        json={"target": "published", "current_status": "sent"},
        headers=BEARER_HEADERS,
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_bill_status"

    disallowed = api.client.post(
        f"{_detail_url()}/transitions",
        json={"target": "paid", "current_status": "draft"},
        headers=BEARER_HEADERS,
    )
    assert disallowed.status_code == 409
    assert disallowed.json()["code"] == "invalid_status_transition"

    unknown = api.client.post(
        f"{_detail_url()}/transitions",
        json={"target": "unknown"},
        headers=BEARER_HEADERS,
    )
    assert unknown.status_code == 422

    api.state.role = "viewer"
    viewer = api.client.post(
        f"{_detail_url()}/transitions",
        json={"target": "published"},
        headers=BEARER_HEADERS,
    )
    assert viewer.status_code == 403
    assert api.services.bill.change_status.call_count == 0


def test_transition_maps_service_race_rejection_to_conflict(api: BillsAPI) -> None:
    api.services.bill.change_status.side_effect = InvalidStatusTransition("draft", "published")
    response = api.client.post(
        f"{_detail_url()}/transitions",
        json={"target": "published"},
        headers=BEARER_HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "invalid_status_transition"


def test_transition_maps_atomic_compare_and_swap_loss_to_stable_conflict(api: BillsAPI) -> None:
    stale_bill = BILL.model_copy(deep=True)
    api.services.bill.get_bill_by_uuid.side_effect = lambda uuid: stale_bill if uuid == BILL.uuid else None
    stale_repo = MagicMock()
    stale_repo.update_status.return_value = False
    stale_service = BillService(stale_repo, MagicMock())
    api.services.bill.change_status.side_effect = stale_service.change_status

    response = api.client.post(
        f"{_detail_url()}/transitions",
        json={"target": "published", "current_status": "draft"},
        headers=BEARER_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "stale_bill_status"
    api.services.audit.safe_log_for.assert_not_called()


def test_status_transition_does_not_require_pix(api: BillsAPI) -> None:
    api.state.role = "manager"
    api.state.pix_missing = True
    response = api.client.post(
        f"{_detail_url()}/transitions",
        json={"target": "published"},
        headers=BEARER_HEADERS,
    )
    assert response.status_code == 200


def test_regenerate_requires_manager_and_pix_then_preserves_service_job_behavior(api: BillsAPI) -> None:
    api.state.role = "manager"
    response = api.client.post(f"{_detail_url()}/regenerate", headers=BEARER_HEADERS)
    assert response.status_code == 202
    api.services.bill.regenerate_pdf.assert_called_once_with(BILL, BILLING, actor=api.state.principal.actor)
    audit = api.services.audit.safe_log_for.call_args
    assert audit.args[1] == AuditEventType.BILL_REGENERATE_PDF
    assert audit.kwargs["previous_state"] == {"pdf_render_status": "succeeded"}
    assert _analytics_headers(response) == {
        "x-rentivo-analytics-event": "rentivo_bill_regenerated",
        "x-rentivo-analytics-bill-uuid-hash": analytics_hash(BILL.uuid),
    }

    api.services.bill.reset_mock()
    api.state.pix_missing = True
    denied = api.client.post(f"{_detail_url()}/regenerate", headers=BEARER_HEADERS)
    assert denied.status_code == 409
    api.services.bill.regenerate_pdf.assert_not_called()


def test_delete_bill_is_owner_admin_only_and_not_pix_gated(api: BillsAPI) -> None:
    api.state.role = "manager"
    denied = api.client.delete(_detail_url(), headers=BEARER_HEADERS)
    assert denied.status_code == 403

    api.state.role = "admin"
    api.state.pix_missing = True
    mutation_order: list[str] = []
    api.services.bill.delete_bill.side_effect = lambda _bill_id: mutation_order.append("db")
    api.services.storage_cleanup.enqueue_bill_delete_cascade.side_effect = lambda _actor, _bill: mutation_order.append(
        "cleanup"
    )
    response = api.client.delete(_detail_url(), headers=BEARER_HEADERS)
    assert response.status_code == 204
    assert mutation_order == ["db", "cleanup"]
    api.services.storage_cleanup.enqueue_bill_delete_cascade.assert_called_once_with(api.state.principal.actor, BILL)
    api.services.bill.delete_bill.assert_called_once_with(BILL.id)
    assert api.services.audit.safe_log_for.call_args.args[1] == AuditEventType.BILL_DELETE
    assert _analytics_headers(response) == {
        "x-rentivo-analytics-event": "rentivo_bill_deleted",
        "x-rentivo-analytics-bill-uuid-hash": analytics_hash(BILL.uuid),
    }


def test_stale_bill_delete_is_conflict_and_never_enqueues_cleanup(api: BillsAPI) -> None:
    stale_repo = MagicMock()
    stale_repo.delete.return_value = False
    stale_service = BillService(stale_repo, MagicMock())
    api.services.bill.delete_bill.side_effect = stale_service.delete_bill

    response = api.client.delete(_detail_url(), headers=BEARER_HEADERS)

    assert response.status_code == 409
    assert response.json()["code"] == "stale_bill_delete"
    api.services.storage_cleanup.enqueue_bill_delete_cascade.assert_not_called()
    api.services.audit.safe_log_for.assert_not_called()


def test_invoice_download_requires_file_scope_and_existing_pdf(api: BillsAPI) -> None:
    api.set_scopes(APIScope.BILLS_READ)
    missing_scope = api.client.get(f"{_detail_url()}/invoice", headers=BEARER_HEADERS)
    assert missing_scope.status_code == 403

    api.set_scopes(APIScope.FILES_READ)
    no_pdf = _updated_bill(BILL, pdf_path=None)
    api.services.bill.get_bill_by_uuid.side_effect = lambda uuid: no_pdf if uuid == BILL.uuid else None
    missing = api.client.get(f"{_detail_url()}/invoice", headers=BEARER_HEADERS)
    assert missing.status_code == 404
    api.services.bill.get_invoice_ref.assert_not_called()


def test_invoice_download_resolves_remote_and_local_files_through_storage(api: BillsAPI, tmp_path) -> None:
    remote = api.client.get(f"{_detail_url()}/invoice", headers=BEARER_HEADERS, follow_redirects=False)
    assert remote.status_code == 302
    assert remote.headers["location"] == "https://files.example/invoice.pdf"
    api.services.bill.get_invoice_ref.assert_called_once_with(BILL)

    invoice = tmp_path / "invoice.pdf"
    invoice.write_bytes(b"%PDF-local")
    api.services.bill.get_invoice_ref.return_value = FileRef(kind="local", location=str(invoice))
    local = api.client.get(f"{_detail_url()}/invoice", headers=BEARER_HEADERS)
    assert local.status_code == 200
    assert local.content == b"%PDF-local"
    assert local.headers["content-type"].startswith("application/pdf")
    assert "private/invoice.pdf" not in local.headers.get("content-disposition", "")


def test_recibo_requires_paid_status_and_audits_stored_download(api: BillsAPI) -> None:
    unpaid = api.client.get(f"{_detail_url()}/recibo", headers=BEARER_HEADERS)
    assert unpaid.status_code == 409
    assert unpaid.json()["code"] == "recibo_unavailable"
    api.services.audit.safe_log_for.assert_not_called()

    paid = _updated_bill(BILL, status="paid", recibo_pdf_path="private/recibo.pdf")
    api.services.bill.get_bill_by_uuid.side_effect = lambda uuid: paid if uuid == BILL.uuid else None
    stored = api.client.get(f"{_detail_url()}/recibo", headers=BEARER_HEADERS, follow_redirects=False)
    assert stored.status_code == 302
    assert stored.headers["location"] == "https://files.example/recibo.pdf"
    assert api.services.audit.safe_log_for.call_args.args[1] == AuditEventType.BILL_RECIBO_DOWNLOAD
    assert _analytics_headers(stored) == {
        "x-rentivo-analytics-event": "rentivo_recibo_downloaded",
        "x-rentivo-analytics-bill-uuid-hash": analytics_hash(BILL.uuid),
    }


@pytest.mark.parametrize("stored", [True, False])
def test_recibo_does_not_audit_when_storage_or_render_resolution_fails(api: BillsAPI, stored: bool) -> None:
    paid = _updated_bill(BILL, status="paid", recibo_pdf_path="private/recibo.pdf" if stored else None)
    api.services.bill.get_bill_by_uuid.side_effect = lambda uuid: paid if uuid == BILL.uuid else None
    if stored:
        api.services.bill.get_recibo_ref.side_effect = RuntimeError("storage unavailable")
    else:
        api.services.bill.render_recibo.side_effect = RuntimeError("render failed")

    with pytest.raises(RuntimeError):
        api.client.get(f"{_detail_url()}/recibo", headers=BEARER_HEADERS)

    api.services.audit.safe_log_for.assert_not_called()


def test_recibo_falls_back_to_inline_render_when_stored_file_is_pending(api: BillsAPI) -> None:
    paid = _updated_bill(BILL, status="paid", recibo_pdf_path=None)
    api.services.bill.get_bill_by_uuid.side_effect = lambda uuid: paid if uuid == BILL.uuid else None

    response = api.client.get(f"{_detail_url()}/recibo", headers=BEARER_HEADERS)

    assert response.status_code == 200
    assert response.content == b"%PDF-recibo"
    assert response.headers["content-disposition"] == f'attachment; filename="recibo-{BILL.uuid}.pdf"'
    api.services.bill.render_recibo.assert_called_once_with(paid, BILLING)


def test_recibo_download_handshake_returns_remote_url_and_audits_once(api: BillsAPI) -> None:
    paid = _updated_bill(BILL, status="paid", recibo_pdf_path="private/recibo.pdf")
    api.services.bill.get_bill_by_uuid.side_effect = lambda uuid: paid if uuid == BILL.uuid else None

    response = api.client.get(f"{_detail_url()}/recibo/download", headers=BEARER_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "download_url": "https://files.example/recibo.pdf",
        "filename": f"recibo-{BILL.uuid}.pdf",
    }
    api.services.bill.get_recibo_ref.assert_called_once_with(paid)
    assert api.services.audit.safe_log_for.call_count == 1
    assert api.services.audit.safe_log_for.call_args.args[1] == AuditEventType.BILL_RECIBO_DOWNLOAD
    assert _analytics_headers(response) == {
        "x-rentivo-analytics-event": "rentivo_recibo_downloaded",
        "x-rentivo-analytics-bill-uuid-hash": analytics_hash(BILL.uuid),
    }


def test_recibo_download_handshake_local_content_route_audits_once_end_to_end(
    api: BillsAPI,
    tmp_path,
) -> None:
    paid = _updated_bill(BILL, status="paid", recibo_pdf_path="private/recibo.pdf")
    local_file = tmp_path / "recibo.pdf"
    local_file.write_bytes(b"%PDF-local")
    api.services.bill.get_bill_by_uuid.side_effect = lambda uuid: paid if uuid == BILL.uuid else None
    api.services.bill.get_recibo_ref.return_value = FileRef(kind="local", location=str(local_file))

    response = api.client.get(f"{_detail_url()}/recibo/download", headers=BEARER_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "download_url": f"http://testserver{_detail_url()}/recibo/content",
        "filename": f"recibo-{BILL.uuid}.pdf",
    }
    assert str(local_file) not in response.text
    api.services.audit.safe_log_for.assert_not_called()
    assert _analytics_headers(response) == {
        "x-rentivo-analytics-event": "rentivo_recibo_downloaded",
        "x-rentivo-analytics-bill-uuid-hash": analytics_hash(BILL.uuid),
    }
    content = api.client.get(response.json()["download_url"], headers=BEARER_HEADERS)
    assert content.status_code == 200
    assert content.content == b"%PDF-local"
    assert content.headers["content-disposition"] == f'attachment; filename="recibo-{BILL.uuid}.pdf"'
    assert _analytics_headers(content) == {}
    assert api.services.audit.safe_log_for.call_count == 1


def test_recibo_content_route_audits_direct_url_storage_redirect(api: BillsAPI) -> None:
    paid = _updated_bill(BILL, status="paid", recibo_pdf_path="private/recibo.pdf")
    api.services.bill.get_bill_by_uuid.side_effect = lambda uuid: paid if uuid == BILL.uuid else None

    response = api.client.get(
        f"{_detail_url()}/recibo/content",
        headers=BEARER_HEADERS,
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "https://files.example/recibo.pdf"
    assert api.services.audit.safe_log_for.call_count == 1
    assert api.services.audit.safe_log_for.call_args.args[1] == AuditEventType.BILL_RECIBO_DOWNLOAD
    assert _analytics_headers(response) == {}


def test_recibo_content_route_requires_scope_paid_and_ready_receipt(api: BillsAPI) -> None:
    url = f"{_detail_url()}/recibo/content"
    api.set_scopes(APIScope.BILLS_READ)
    missing_scope = api.client.get(url, headers=BEARER_HEADERS)
    assert missing_scope.status_code == 403

    api.set_scopes(APIScope.FILES_READ)
    unpaid = api.client.get(url, headers=BEARER_HEADERS)
    assert unpaid.status_code == 409
    assert unpaid.json()["code"] == "recibo_unavailable"

    pending = _updated_bill(BILL, status="paid", recibo_pdf_path=None)
    api.services.bill.get_bill_by_uuid.side_effect = lambda uuid: pending if uuid == BILL.uuid else None
    not_ready = api.client.get(url, headers=BEARER_HEADERS)
    assert not_ready.status_code == 409
    assert not_ready.json()["code"] == "recibo_not_ready"
    api.services.bill.get_recibo_ref.assert_not_called()
    api.services.audit.safe_log_for.assert_not_called()


def test_recibo_download_handshake_requires_scope_paid_and_ready_receipt(api: BillsAPI) -> None:
    api.set_scopes(APIScope.BILLS_READ)
    missing_scope = api.client.get(f"{_detail_url()}/recibo/download", headers=BEARER_HEADERS)
    assert missing_scope.status_code == 403

    api.set_scopes(APIScope.FILES_READ)
    unpaid = api.client.get(f"{_detail_url()}/recibo/download", headers=BEARER_HEADERS)
    assert unpaid.status_code == 409
    assert unpaid.json()["code"] == "recibo_unavailable"

    pending = _updated_bill(BILL, status="paid", recibo_pdf_path=None)
    api.services.bill.get_bill_by_uuid.side_effect = lambda uuid: pending if uuid == BILL.uuid else None
    not_ready = api.client.get(f"{_detail_url()}/recibo/download", headers=BEARER_HEADERS)
    assert not_ready.status_code == 409
    assert not_ready.json()["code"] == "recibo_not_ready"
    api.services.bill.get_recibo_ref.assert_not_called()
    api.services.audit.safe_log_for.assert_not_called()


def test_recibo_download_handshake_does_not_audit_failed_storage_resolution(api: BillsAPI) -> None:
    paid = _updated_bill(BILL, status="paid", recibo_pdf_path="private/recibo.pdf")
    api.services.bill.get_bill_by_uuid.side_effect = lambda uuid: paid if uuid == BILL.uuid else None
    api.services.bill.get_recibo_ref.side_effect = RuntimeError("storage unavailable")

    with pytest.raises(RuntimeError, match="storage unavailable"):
        api.client.get(f"{_detail_url()}/recibo/download", headers=BEARER_HEADERS)

    api.services.audit.safe_log_for.assert_not_called()


def test_receipt_list_and_download_enforce_file_scope_and_full_parent_chain(api: BillsAPI) -> None:
    list_response = api.client.get(f"{_detail_url()}/receipts", headers=BEARER_HEADERS)
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["uuid"] == RECEIPT.uuid
    assert "storage_key" not in list_response.text

    mismatch = api.client.get(f"{_detail_url()}/receipts/{OTHER_RECEIPT.uuid}", headers=BEARER_HEADERS)
    assert mismatch.status_code == 404

    remote = api.client.get(
        f"{_detail_url()}/receipts/{RECEIPT.uuid}",
        headers=BEARER_HEADERS,
        follow_redirects=False,
    )
    assert remote.status_code == 302
    assert remote.headers["location"] == "https://files.example/receipt.pdf"
    api.services.bill.get_receipt_ref.assert_called_once_with(RECEIPT)


def test_receipt_download_streams_local_content_with_recorded_mime(api: BillsAPI, tmp_path) -> None:
    receipt_file = tmp_path / "proof.png"
    receipt_file.write_bytes(b"png")
    png_receipt = RECEIPT.model_copy(
        update={"filename": "proof.png", "content_type": "image/png", "storage_key": "private/proof.png"}
    )
    api.services.bill.get_receipt_by_uuid.side_effect = lambda uuid: png_receipt if uuid == RECEIPT.uuid else None
    api.services.bill.get_receipt_ref.return_value = FileRef(kind="local", location=str(receipt_file))

    response = api.client.get(f"{_detail_url()}/receipts/{RECEIPT.uuid}", headers=BEARER_HEADERS)

    assert response.status_code == 200
    assert response.content == b"png"
    assert response.headers["content-type"].startswith("image/png")


def test_receipt_download_rejects_row_without_storage_key(api: BillsAPI) -> None:
    missing_file = RECEIPT.model_copy(update={"storage_key": ""})
    api.services.bill.get_receipt_by_uuid.side_effect = lambda uuid: missing_file if uuid == RECEIPT.uuid else None
    response = api.client.get(f"{_detail_url()}/receipts/{RECEIPT.uuid}", headers=BEARER_HEADERS)
    assert response.status_code == 404
    api.services.bill.get_receipt_ref.assert_not_called()


def test_receipt_upload_validates_each_file_audits_and_renders_once(api: BillsAPI) -> None:
    response = api.client.post(
        f"{_detail_url()}/receipts",
        files=[
            ("receipt_files", ("ok.pdf", b"%PDF-ok", "application/pdf")),
            ("receipt_files", ("bad.gif", b"gif", "image/gif")),
            ("receipt_files", ("empty.pdf", b"", "application/pdf")),
            ("receipt_files", ("big.pdf", b"x" * (MAX_RECEIPT_SIZE + 1), "application/pdf")),
        ],
        headers=BEARER_HEADERS,
    )

    assert response.status_code == 201
    assert response.json()["attached"] == 1
    assert response.json()["skipped"] == 3
    assert response.json()["total_bytes"] == 7
    api.services.bill.add_receipt.assert_called_once()
    assert api.services.bill.add_receipt.call_args.kwargs["render"] is False
    api.services.bill.regenerate_pdf.assert_called_once_with(BILL, BILLING, actor=api.state.principal.actor)
    assert api.services.audit.safe_log_for.call_args.args[1] == AuditEventType.RECEIPT_UPLOAD
    assert _analytics_headers(response) == {
        "x-rentivo-analytics-event": "rentivo_receipt_uploaded",
        "x-rentivo-analytics-bill-uuid-hash": analytics_hash(BILL.uuid),
        "x-rentivo-analytics-count": "1",
        "x-rentivo-analytics-total-bytes": "7",
    }


def test_receipt_batch_reads_and_validates_every_file_before_first_mutation(api: BillsAPI) -> None:
    events: list[str] = []
    uploads = [
        SimpleNamespace(
            filename="a.pdf",
            content_type="application/pdf",
            read=AsyncMock(side_effect=lambda: events.append("read-a") or b"a"),
        ),
        SimpleNamespace(
            filename="b.pdf",
            content_type="application/pdf",
            read=AsyncMock(side_effect=lambda: events.append("read-b") or b"b"),
        ),
    ]
    api.services.bill.add_receipt.side_effect = lambda **_kwargs: (
        events.append("add") or RECEIPT,
        [],
    )
    routes = import_module("rentivo.api.routes.bills")
    access = routes.BillAccess(bill=BILL, billing=BILLING, role="owner", principal=api.state.principal)

    asyncio.run(routes._upload_receipts(uploads, access, api.services, regenerate=False))

    assert events == ["read-a", "read-b", "add", "add"]


def test_receipt_batch_rolls_back_partial_upload_when_later_storage_write_fails(api: BillsAPI) -> None:
    first_receipt = RECEIPT.model_copy(update={"id": 71})
    api.services.bill.add_receipt.side_effect = [(first_receipt, []), RuntimeError("storage failed")]

    with pytest.raises(RuntimeError, match="storage failed"):
        api.client.post(
            f"{_detail_url()}/receipts",
            files=[
                ("receipt_files", ("a.pdf", b"%PDF-a", "application/pdf")),
                ("receipt_files", ("b.pdf", b"%PDF-b", "application/pdf")),
            ],
            headers=BEARER_HEADERS,
        )

    api.services.bill.rollback_receipt_batch.assert_called_once_with((first_receipt,))
    api.services.bill.regenerate_pdf.assert_not_called()
    api.services.audit.safe_log_for.assert_not_called()


def test_receipt_batch_keeps_uploads_when_render_scheduling_fails(api: BillsAPI) -> None:
    attached = RECEIPT.model_copy(update={"id": 71})
    api.services.bill.add_receipt.side_effect = [(attached, [])]
    api.services.bill.regenerate_pdf.side_effect = RuntimeError("render enqueue failed")

    with pytest.raises(RuntimeError, match="render enqueue failed"):
        api.client.post(
            f"{_detail_url()}/receipts",
            files=[("receipt_files", ("a.pdf", b"%PDF-a", "application/pdf"))],
            headers=BEARER_HEADERS,
        )

    api.services.bill.rollback_receipt_batch.assert_not_called()
    api.services.audit.safe_log_for.assert_called_once()
    assert api.services.audit.safe_log_for.call_args.args[1] == AuditEventType.RECEIPT_UPLOAD


def test_receipt_batch_real_job_failure_keeps_receipt_and_marks_render_failed(
    db_connection,
    fake_encryption,
    sample_billing,
    sample_bill,
    tmp_path,
) -> None:
    billing_repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
    bill_repo = SQLAlchemyBillRepository(db_connection, fake_encryption)
    receipt_repo = SQLAlchemyReceiptRepository(db_connection, fake_encryption)
    billing = billing_repo.create(sample_billing())
    bill = bill_repo.create(sample_bill(billing_id=billing.id))
    bill_repo.update_pdf_render_status(bill.id, "succeeded")
    bill.pdf_render_status = "succeeded"
    backend = _AlwaysFailJobBackend()
    service = BillService(
        bill_repo,
        LocalStorage(str(tmp_path)),
        receipt_repo,
        job_service=JobService(backend, MagicMock()),
    )
    routes = import_module("rentivo.api.routes.bills")
    principal = SimpleNamespace(
        actor=SimpleNamespace(source="integration", user_id=7, email="bills@example.com"),
    )
    access = routes.BillAccess(bill=bill, billing=billing, role="owner", principal=principal)
    services = SimpleNamespace(bill=service, audit=MagicMock())
    uploads = (
        routes._ValidatedReceiptUpload(
            filename="receipt.pdf",
            file_bytes=b"%PDF-receipt",
            content_type="application/pdf",
        ),
    )

    with pytest.raises(RuntimeError, match="job backend failed"):
        routes._attach_receipts(uploads, 0, access, services, regenerate=True, audit=True)

    persisted = bill_repo.get_by_id(bill.id)
    assert persisted is not None
    assert persisted.pdf_render_status == "failed"
    assert bill.pdf_render_status == "failed"
    receipts = receipt_repo.list_by_bill(bill.id)
    assert len(receipts) == 1
    assert receipts[0].filename == "receipt.pdf"
    assert backend.queued == []
    assert len([path for path in tmp_path.rglob("*") if path.is_file()]) == 1
    services.audit.safe_log_for.assert_called_once()
    assert services.audit.safe_log_for.call_args.args[1] == AuditEventType.RECEIPT_UPLOAD


def test_receipt_upload_with_no_valid_files_does_not_render(api: BillsAPI) -> None:
    response = api.client.post(
        f"{_detail_url()}/receipts",
        files=[("receipt_files", ("bad.gif", b"gif", "image/gif"))],
        headers=BEARER_HEADERS,
    )
    assert response.status_code == 201
    assert response.json()["attached"] == 0
    api.services.bill.regenerate_pdf.assert_not_called()


def test_receipt_upload_rejects_blank_filename_before_service_call(api: BillsAPI) -> None:
    response = api.client.post(
        f"{_detail_url()}/receipts",
        files=[("receipt_files", ("", b"%PDF-blank", "application/pdf"))],
        headers=BEARER_HEADERS,
    )
    assert response.status_code == 422
    api.services.bill.add_receipt.assert_not_called()
    api.services.bill.regenerate_pdf.assert_not_called()


def test_receipt_upload_requires_file_write_manager_and_pix(api: BillsAPI) -> None:
    url = f"{_detail_url()}/receipts"
    files = [("receipt_files", ("ok.pdf", b"%PDF-ok", "application/pdf"))]
    api.set_scopes(APIScope.BILLS_WRITE)
    scope = api.client.post(url, files=files, headers=BEARER_HEADERS)
    assert scope.status_code == 403

    api.set_scopes(APIScope.FILES_WRITE)
    api.state.role = "viewer"
    role = api.client.post(url, files=files, headers=BEARER_HEADERS)
    assert role.status_code == 403

    api.state.role = "manager"
    api.state.pix_missing = True
    pix = api.client.post(url, files=files, headers=BEARER_HEADERS)
    assert pix.status_code == 409


def test_delete_receipt_checks_linkage_then_audits_and_enqueues_durable_cleanup(api: BillsAPI) -> None:
    mismatch = api.client.delete(
        f"{_detail_url()}/receipts/{OTHER_RECEIPT.uuid}",
        headers=BEARER_HEADERS,
    )
    assert mismatch.status_code == 404
    api.services.bill.delete_receipt.assert_not_called()

    api.state.pix_missing = True
    response = api.client.delete(
        f"{_detail_url()}/receipts/{RECEIPT.uuid}",
        headers=BEARER_HEADERS,
    )
    assert response.status_code == 204
    api.services.bill.delete_receipt.assert_called_once_with(
        RECEIPT,
        BILL,
        BILLING,
        actor=api.state.principal.actor,
    )
    api.services.storage_cleanup.enqueue_receipt_delete.assert_not_called()
    audit = api.services.audit.safe_log_for.call_args
    assert audit.args[1] == AuditEventType.RECEIPT_DELETE
    assert audit.kwargs["previous_state"]["filename"] == RECEIPT.filename
    assert _analytics_headers(response) == {
        "x-rentivo-analytics-event": "rentivo_receipt_deleted",
        "x-rentivo-analytics-bill-uuid-hash": analytics_hash(BILL.uuid),
    }


def test_delete_receipt_maps_lost_render_ownership_to_conflict(api: BillsAPI) -> None:
    api.services.bill.delete_receipt.side_effect = StaleReceiptDeleteError

    response = api.client.delete(
        f"{_detail_url()}/receipts/{RECEIPT.uuid}",
        headers=BEARER_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "stale_receipt_delete"
    api.services.audit.safe_log_for.assert_not_called()


def test_reorder_receipts_uses_exact_complete_order_and_is_not_pix_gated(api: BillsAPI) -> None:
    api.state.role = "manager"
    api.state.pix_missing = True
    response = api.client.put(
        f"{_detail_url()}/receipt-order",
        json={"order": [RECEIPT.uuid]},
        headers=BEARER_HEADERS,
    )
    assert response.status_code == 200
    api.services.bill.reorder_receipts.assert_called_once_with(
        BILL,
        BILLING,
        [RECEIPT.uuid],
        actor=api.state.principal.actor,
    )
    assert api.services.audit.safe_log_for.call_args.args[1] == AuditEventType.RECEIPT_REORDER


def test_reorder_receipts_rejects_duplicates_and_service_conflicts(api: BillsAPI) -> None:
    duplicate = api.client.put(
        f"{_detail_url()}/receipt-order",
        json={"order": [RECEIPT.uuid, RECEIPT.uuid]},
        headers=BEARER_HEADERS,
    )
    assert duplicate.status_code == 422

    api.services.bill.reorder_receipts.side_effect = ValueError("Must include all receipts in the new order")
    incomplete = api.client.put(
        f"{_detail_url()}/receipt-order",
        json={"order": []},
        headers=BEARER_HEADERS,
    )
    assert incomplete.status_code == 409
    assert incomplete.json()["code"] == "invalid_receipt_order"


@pytest.mark.parametrize(
    "identifier",
    ["not-a-public-id", "01J0000000000000000000000", "01J0000000000000000000000I", "01j00000000000000000000000"],
)
def test_reorder_receipts_rejects_malformed_public_identifiers(api: BillsAPI, identifier: str) -> None:
    response = api.client.put(
        f"{_detail_url()}/receipt-order",
        json={"order": [identifier]},
        headers=BEARER_HEADERS,
    )

    assert response.status_code == 422
    api.services.bill.reorder_receipts.assert_not_called()


def test_file_metadata_never_serializes_internal_ids_or_storage_keys(api: BillsAPI) -> None:
    response = api.client.get(_detail_url(), headers=BEARER_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert "id" not in body
    assert "billing_id" not in body
    assert "bill_id" not in json.dumps(body["receipts"])
    assert "storage_key" not in json.dumps(body["receipts"])
