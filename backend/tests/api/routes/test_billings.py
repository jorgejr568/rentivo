from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.responses import Response

from rentivo.api.app import create_app
from rentivo.api.csrf import CSRF_HEADER_NAME, issue_csrf_token
from rentivo.api.dependencies import get_services
from rentivo.api.principal import Principal
from rentivo.api.routes.billings import router as billings_router
from rentivo.constants.api_scopes import ALL_FIRST_PARTY_SCOPES, APIScope
from rentivo.models.api_key import APIKey, APIKeyGrant
from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import Bill, BillSummary
from rentivo.models.billing import Billing, BillingItem, ItemType
from rentivo.models.billing_attachment import BillingAttachment
from rentivo.models.communication import Communication, CommunicationTemplate
from rentivo.models.expense import Expense
from rentivo.models.organization import Organization, OrganizationMember
from rentivo.models.recipient import Recipient
from rentivo.models.user import User
from rentivo.services.billing_stats import BillingStats
from rentivo.settings import settings
from rentivo.storage.base import FileRef

NOW = datetime(2026, 7, 18, 12, tzinfo=UTC)
LOGIN_SECRET = f"rntv-v1-{'L' * 43}"
INTEGRATION_SECRET = f"rntv-v1-{'I' * 43}"
ORG_ONLY_SECRET = f"rntv-v1-{'O' * 43}"
NO_SCOPE_SECRET = f"rntv-v1-{'N' * 43}"

USER = User(id=7, email="person@example.com", pix_key="")
OTHER_USER = User(id=8, email="other@example.com")
ORGANIZATION = Organization(id=31, uuid="org-31", name="Administradora Exemplo", created_by=USER.id)
OTHER_ORGANIZATION = Organization(id=32, uuid="org-32", name="Organizacao sem acesso", created_by=OTHER_USER.id)

PERSONAL_BILLING = Billing(
    id=11,
    uuid="billing-personal",
    name="Apartamento 101",
    description="Inquilino atual",
    owner_type="user",
    owner_id=USER.id,
    items=[BillingItem(id=101, description="Aluguel", amount=285_000, item_type=ItemType.FIXED)],
    created_at=NOW,
    updated_at=NOW,
)
ORG_BILLING = Billing(
    id=12,
    uuid="billing-org",
    name="Sala comercial",
    owner_type="organization",
    owner_id=ORGANIZATION.id,
    items=[BillingItem(id=102, description="Aluguel", amount=450_000, item_type=ItemType.FIXED)],
)
OTHER_ORG_BILLING = Billing(
    id=13,
    uuid="billing-other-org",
    name="Fora do acesso",
    owner_type="organization",
    owner_id=OTHER_ORGANIZATION.id,
    items=[BillingItem(id=103, description="Aluguel", amount=100_000, item_type=ItemType.FIXED)],
)
PERSONAL_BILL = Bill(
    id=41,
    uuid="bill-personal",
    billing_id=PERSONAL_BILLING.id,
    reference_month="2026-07",
    total_amount=285_000,
    pdf_path="invoices/bill-personal.pdf",
    due_date="2026-07-10",
)
FOREIGN_BILL = Bill(
    id=42,
    uuid="bill-foreign",
    billing_id=ORG_BILLING.id,
    reference_month="2026-07",
    total_amount=450_000,
    pdf_path="invoices/bill-foreign.pdf",
)


def _key(
    key_id: int,
    *,
    login: bool,
    scopes: frozenset[str] = ALL_FIRST_PARTY_SCOPES,
    grants: tuple[APIKeyGrant, ...] = (),
) -> APIKey:
    return APIKey(
        id=key_id,
        uuid=f"key-{key_id}",
        user_id=USER.id,
        name="Browser" if login else "Integracao",
        secret_hash=bytes([key_id]) * 32,
        key_start="abcd",
        key_end="yz",
        is_login_token=login,
        scopes=scopes,
        grants=grants,
        expires_at=NOW + timedelta(days=30),
    )


LOGIN_KEY = _key(1, login=True)
INTEGRATION_KEY = _key(
    2,
    login=False,
    grants=(APIKeyGrant(resource_type="user", resource_id=USER.id),),
)
ORG_ONLY_KEY = _key(
    3,
    login=False,
    grants=(APIKeyGrant(resource_type="organization", resource_id=ORGANIZATION.id),),
)
NO_SCOPE_KEY = _key(4, login=False, scopes=frozenset(), grants=INTEGRATION_KEY.grants)


class FakeUserService:
    @staticmethod
    def get_by_id(user_id: int) -> User | None:
        return {USER.id: USER, OTHER_USER.id: OTHER_USER}.get(user_id)


class FakeOrganizationService:
    def __init__(self) -> None:
        self.organizations = {ORGANIZATION.id: ORGANIZATION, OTHER_ORGANIZATION.id: OTHER_ORGANIZATION}
        self.members: dict[tuple[int, int], OrganizationMember] = {
            (ORGANIZATION.id, USER.id): OrganizationMember(
                organization_id=ORGANIZATION.id,
                user_id=USER.id,
                email=USER.email,
                role="admin",
            ),
            (OTHER_ORGANIZATION.id, OTHER_USER.id): OrganizationMember(
                organization_id=OTHER_ORGANIZATION.id,
                user_id=OTHER_USER.id,
                email=OTHER_USER.email,
                role="admin",
            ),
        }

    def get_by_id(self, organization_id: int) -> Organization | None:
        return self.organizations.get(organization_id)

    def get_by_uuid(self, organization_uuid: str) -> Organization | None:
        return next((org for org in self.organizations.values() if org.uuid == organization_uuid), None)

    def get_member(self, organization_id: int, user_id: int) -> OrganizationMember | None:
        return self.members.get((organization_id, user_id))

    def list_members(self, organization_id: int) -> list[OrganizationMember]:
        return [member for (org_id, _user_id), member in self.members.items() if org_id == organization_id]


class FakeAPIKeyService:
    def __init__(self, organizations: FakeOrganizationService) -> None:
        self.organizations = organizations
        self.credentials = {
            LOGIN_SECRET: LOGIN_KEY,
            INTEGRATION_SECRET: INTEGRATION_KEY,
            ORG_ONLY_SECRET: ORG_ONLY_KEY,
            NO_SCOPE_SECRET: NO_SCOPE_KEY,
        }

    def authenticate(self, secret: str) -> APIKey | None:
        return self.credentials.get(secret)

    def can_access_resource(self, key: APIKey, resource_type: str, resource_id: int) -> bool:
        if resource_type == "user":
            return resource_id == key.user_id and (
                key.is_login_token or APIKeyGrant(resource_type="user", resource_id=resource_id) in key.grants
            )
        if resource_type != "organization":
            return False
        has_grant = (
            key.is_login_token or APIKeyGrant(resource_type="organization", resource_id=resource_id) in key.grants
        )
        return has_grant and self.organizations.get_member(resource_id, key.user_id) is not None


class FakeAuthorizationService:
    def __init__(self, organizations: FakeOrganizationService) -> None:
        self.organizations = organizations
        self.role_overrides: dict[int, str | None] = {}

    def get_role_for_billing(self, user_id: int, billing: Billing) -> str | None:
        if billing.id in self.role_overrides:
            return self.role_overrides[billing.id]
        if billing.owner_type == "user":
            return "owner" if billing.owner_id == user_id else None
        member = self.organizations.get_member(billing.owner_id, user_id)
        return member.role if member is not None else None


class FakeBillingService:
    def __init__(self) -> None:
        self.billings = [
            PERSONAL_BILLING.model_copy(deep=True),
            ORG_BILLING.model_copy(deep=True),
            OTHER_ORG_BILLING.model_copy(deep=True),
        ]
        self.create_calls: list[dict[str, Any]] = []
        self.update_calls: list[Billing] = []
        self.delete_calls: list[int] = []
        self.transfer_calls: list[tuple[int, int]] = []
        self.create_error: ValueError | None = None
        self.update_error: ValueError | None = None
        self.transfer_error: ValueError | None = None

    def list_billings_for_user(self, user_id: int) -> list[Billing]:
        assert user_id == USER.id
        return list(self.billings)

    def get_billing_by_uuid(self, billing_uuid: str) -> Billing | None:
        return next((billing for billing in self.billings if billing.uuid == billing_uuid), None)

    def create_billing(
        self,
        name: str,
        description: str,
        items: list[BillingItem],
        *,
        pix_key: str,
        pix_merchant_name: str,
        pix_merchant_city: str,
        owner_type: str,
        owner_id: int,
    ) -> Billing:
        if self.create_error is not None:
            raise self.create_error
        self.create_calls.append(
            {
                "name": name,
                "description": description,
                "items": items,
                "pix_key": pix_key,
                "pix_merchant_name": pix_merchant_name,
                "pix_merchant_city": pix_merchant_city,
                "owner_type": owner_type,
                "owner_id": owner_id,
            }
        )
        billing = Billing(
            id=100 + len(self.create_calls),
            uuid=f"created-{len(self.create_calls)}",
            name=name,
            description=description,
            items=items,
            pix_key=pix_key,
            pix_merchant_name=pix_merchant_name,
            pix_merchant_city=pix_merchant_city,
            owner_type=owner_type,
            owner_id=owner_id,
            created_at=NOW,
            updated_at=NOW,
        )
        self.billings.append(billing)
        return billing

    def update_billing(self, billing: Billing) -> Billing:
        if self.update_error is not None:
            raise self.update_error
        self.update_calls.append(billing.model_copy(deep=True))
        return billing

    def delete_billing(self, billing_id: int) -> None:
        self.delete_calls.append(billing_id)

    def transfer_to_organization(self, billing_id: int, organization_id: int) -> None:
        if self.transfer_error is not None:
            raise self.transfer_error
        self.transfer_calls.append((billing_id, organization_id))


class FakeBillingStatsService:
    def __init__(self) -> None:
        self.calls: list[list[int]] = []
        self.include_current = True

    def stats_for_ids(self, billing_ids: list[int]) -> BillingStats:
        self.calls.append(billing_ids)
        current = (
            {
                billing_id: BillSummary(
                    billing_id=billing_id,
                    total_amount=10_000 * billing_id,
                    status="sent",
                    reference_month="2026-07",
                    due_date="2026-07-10",
                )
                for billing_id in billing_ids
            }
            if self.include_current
            else {}
        )
        return BillingStats(
            year=2026,
            expected=900_000,
            received=300_000,
            pending=500_000,
            overdue=100_000,
            paid_count=1,
            pending_count=2,
            overdue_count=1,
            total_expenses=50_000,
            net_income=250_000,
            current=current,
        )


class FakePixService:
    def __init__(self) -> None:
        self.ready_billing_ids = {ORG_BILLING.id}

    @staticmethod
    def owner_needs_setup(owner_type: str, owner_id: int) -> bool:
        assert (owner_type, owner_id) == ("user", USER.id)
        return True

    def billing_needs_setup(self, billing: Billing) -> bool:
        return billing.id not in self.ready_billing_ids


class FakeRecipientService:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.rows: dict[int, list[Recipient]] = {
            PERSONAL_BILLING.id: [
                Recipient(
                    id=1,
                    uuid=f"{prefix}-existing",
                    billing_id=PERSONAL_BILLING.id,
                    name="Joao",
                    email="joao@example.com",
                )
            ]
        }
        self.replace_calls: list[tuple[int, list[dict[str, str]]]] = []

    def list_for_billing(self, billing_id: int) -> list[Recipient]:
        return list(self.rows.get(billing_id, []))

    def replace_for_billing(self, billing_id: int, rows: list[dict[str, str]]) -> list[Recipient]:
        self.replace_calls.append((billing_id, rows))
        saved = [
            Recipient(
                id=index,
                uuid=f"{self.prefix}-{index}",
                billing_id=billing_id,
                name=row["name"],
                email=row["email"],
                sort_order=index - 1,
            )
            for index, row in enumerate(rows, 1)
        ]
        self.rows[billing_id] = saved
        return saved


class FakeExpenseService:
    def __init__(self) -> None:
        self.rows = [
            Expense(
                id=51,
                uuid="expense-personal",
                billing_id=PERSONAL_BILLING.id,
                description="IPTU 2026",
                amount=120_000,
                category="iptu",
                incurred_on="2026-01-10",
                created_at=NOW,
            ),
            Expense(
                id=52,
                uuid="expense-foreign",
                billing_id=ORG_BILLING.id,
                description="Condominio",
                amount=80_000,
                category="condominio",
                incurred_on="2026-02-10",
            ),
        ]
        self.create_calls: list[dict[str, Any]] = []
        self.delete_calls: list[Expense] = []

    def list_for_billing(self, billing_id: int) -> list[Expense]:
        return [expense for expense in self.rows if expense.billing_id == billing_id]

    def get_by_uuid(self, expense_uuid: str) -> Expense | None:
        return next((expense for expense in self.rows if expense.uuid == expense_uuid), None)

    def create_expense(self, **kwargs: Any) -> Expense:
        self.create_calls.append(kwargs)
        expense = Expense(id=60, uuid="expense-created", created_at=NOW, **kwargs)
        self.rows.append(expense)
        return expense

    def delete_expense(self, expense: Expense) -> None:
        self.delete_calls.append(expense)


class FakeAttachmentService:
    def __init__(self, local_path: Path) -> None:
        self.rows = [
            BillingAttachment(
                id=61,
                uuid="attachment-personal",
                billing_id=PERSONAL_BILLING.id,
                name="Contrato",
                filename="contrato.pdf",
                storage_key="private/contrato.pdf",
                content_type="application/pdf",
                file_size=9,
                created_at=NOW,
            ),
            BillingAttachment(
                id=62,
                uuid="attachment-foreign",
                billing_id=ORG_BILLING.id,
                name="Outro",
                filename="outro.pdf",
                storage_key="private/outro.pdf",
                content_type="application/pdf",
                file_size=5,
            ),
        ]
        self.local_path = local_path
        self.ref = FileRef(kind="local", location=str(local_path))
        self.ref_calls: list[BillingAttachment] = []
        self.add_calls: list[dict[str, Any]] = []
        self.delete_calls: list[BillingAttachment] = []
        self.add_error: ValueError | None = None

    def list_attachments(self, billing_id: int) -> list[BillingAttachment]:
        return [attachment for attachment in self.rows if attachment.billing_id == billing_id]

    def get_attachment_by_uuid(self, attachment_uuid: str) -> BillingAttachment | None:
        return next((attachment for attachment in self.rows if attachment.uuid == attachment_uuid), None)

    def add_attachment(self, **kwargs: Any) -> BillingAttachment:
        if self.add_error is not None:
            raise self.add_error
        self.add_calls.append(kwargs)
        attachment = BillingAttachment(
            id=63,
            uuid="attachment-created",
            billing_id=kwargs["billing"].id,
            name=kwargs["name"].strip() or kwargs["filename"],
            filename=kwargs["filename"],
            storage_key="private/created.pdf",
            content_type=kwargs["content_type"],
            file_size=len(kwargs["file_bytes"]),
            created_at=NOW,
        )
        self.rows.append(attachment)
        return attachment

    def get_attachment_ref(self, attachment: BillingAttachment) -> FileRef:
        self.ref_calls.append(attachment)
        return self.ref

    def delete_attachment(self, attachment: BillingAttachment) -> None:
        self.delete_calls.append(attachment)


class FakeBillService:
    def __init__(self) -> None:
        self.bills = [PERSONAL_BILL.model_copy(), FOREIGN_BILL.model_copy()]

    def get_bill_by_uuid(self, bill_uuid: str) -> Bill | None:
        return next((bill for bill in self.bills if bill.uuid == bill_uuid), None)


class FakeCommunicationService:
    def __init__(self) -> None:
        self.send_calls: list[dict[str, Any]] = []
        self.save_calls: list[tuple[str, int, str, str, str]] = []

    @staticmethod
    def resolve_template(billing: Billing, comm_type: str) -> CommunicationTemplate:
        return CommunicationTemplate(
            owner_type="system",
            owner_id=0,
            comm_type=comm_type,
            subject=f"Assunto {comm_type}",
            body_markdown="Prezado {{nome_inquilino}}",
        )

    def send(self, **kwargs: Any) -> list[Communication]:
        self.send_calls.append(kwargs)
        return [
            Communication(
                id=70 + index,
                uuid=f"communication-{index}",
                bill_id=kwargs["bill"].id,
                comm_type=kwargs["comm_type"],
                recipient_name=recipient.name,
                recipient_email=recipient.email,
                subject=kwargs["subject_template"],
                body_markdown=kwargs["body_template"],
                job_ulid=f"job-{index}",
            )
            for index, recipient in enumerate(kwargs["recipients"], 1)
        ]

    def save_template(self, owner_type: str, owner_id: int, comm_type: str, subject: str, body: str) -> None:
        self.save_calls.append((owner_type, owner_id, comm_type, subject, body))


class CallRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def safe_log_for(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


class FakeJobService:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, str, dict[str, Any]]] = []

    def enqueue_for(self, actor: Any, job_type: str, payload: dict[str, Any]) -> None:
        self.calls.append((actor, job_type, payload))


class FakeStorageCleanupService:
    def __init__(self) -> None:
        self.billing_calls: list[tuple[Any, Billing]] = []
        self.attachment_calls: list[tuple[Any, BillingAttachment]] = []

    def enqueue_billing_delete_cascade(self, actor: Any, billing: Billing) -> None:
        self.billing_calls.append((actor, billing))

    def enqueue_attachment_delete(self, actor: Any, attachment: BillingAttachment) -> None:
        self.attachment_calls.append((actor, attachment))


class FakeBillingNotificationService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def notify_transferred(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


@dataclass(slots=True)
class BillingHarness:
    client: TestClient
    app: Any
    services: Any

    def request(
        self,
        method: str,
        path: str,
        *,
        credential: str = LOGIN_SECRET,
        csrf: bool = True,
        **kwargs: Any,
    ):
        key = self.services.api_key.credentials[credential]
        headers = dict(kwargs.pop("headers", {}))
        if key.is_login_token:
            cookie = f"{settings.access_cookie_name}={credential}"
            if csrf and method.upper() not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
                token = issue_csrf_token(Response(), Principal(user=USER, api_key=key, source="web"))
                cookie = f"{cookie}; {settings.csrf_cookie_name}={token}"
                headers[CSRF_HEADER_NAME] = token
            headers["Cookie"] = cookie
        else:
            headers["Authorization"] = f"Bearer {credential}"
        return self.client.request(method, path, headers=headers, **kwargs)


@pytest.fixture()
def billing_harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> BillingHarness:
    monkeypatch.setattr(settings, "secret_key", "billing-route-contract-signing-key")
    monkeypatch.setattr(settings, "access_cookie_name", "__Host-rentivo_access")
    monkeypatch.setattr(settings, "csrf_cookie_name", "__Host-rentivo_csrf")
    monkeypatch.setattr(settings, "cookie_secure", True)

    local_path = tmp_path / "contrato.pdf"
    local_path.write_bytes(b"%PDF-test")
    organization = FakeOrganizationService()
    services = SimpleNamespace(
        user=FakeUserService(),
        organization=organization,
        api_key=FakeAPIKeyService(organization),
        authorization=FakeAuthorizationService(organization),
        billing=FakeBillingService(),
        billing_stats=FakeBillingStatsService(),
        pix=FakePixService(),
        recipient=FakeRecipientService("recipient"),
        reply_to=FakeRecipientService("reply"),
        expense=FakeExpenseService(),
        billing_attachment=FakeAttachmentService(local_path),
        bill=FakeBillService(),
        communication=FakeCommunicationService(),
        audit=CallRecorder(),
        job=FakeJobService(),
        storage_cleanup=FakeStorageCleanupService(),
        billing_notification=FakeBillingNotificationService(),
    )
    app = create_app()
    app.include_router(billings_router, prefix="/api/v1")
    app.dependency_overrides[get_services] = lambda: services
    return BillingHarness(client=TestClient(app), app=app, services=services)


def _billing_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "  Apartamento novo  ",
        "description": "  Contrato anual  ",
        "pix_key": "",
        "pix_merchant_name": "",
        "pix_merchant_city": "",
        "items": [
            {"description": "  Aluguel  ", "amount": 300_000, "item_type": "fixed"},
            {"description": "  Agua  ", "amount": 0, "item_type": "variable"},
        ],
    }
    payload.update(overrides)
    return payload


def _audit_events(harness: BillingHarness) -> list[Any]:
    return [args[1] for args, _kwargs in harness.services.audit.calls]


def test_new_user_lists_no_billings(billing_harness: BillingHarness) -> None:
    billing_harness.services.billing.billings = []

    response = billing_harness.request("GET", "/api/v1/billings")

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "user_pix_incomplete": True,
        "stats": {
            "year": 2026,
            "expected": 900000,
            "received": 300000,
            "pending": 500000,
            "overdue": 100000,
            "paid_count": 1,
            "pending_count": 2,
            "overdue_count": 1,
            "active_count": 3,
            "billed_count": 4,
            "total_expenses": 50000,
            "net_income": 250000,
        },
    }
    assert billing_harness.services.billing_stats.calls == [[]]


def test_list_intersects_personal_and_organization_billings_with_grants_and_live_roles(
    billing_harness: BillingHarness,
) -> None:
    response = billing_harness.request(
        "GET",
        "/api/v1/billings",
        credential=INTEGRATION_SECRET,
    )

    assert response.status_code == 200
    assert [item["uuid"] for item in response.json()["items"]] == [PERSONAL_BILLING.uuid]
    assert billing_harness.services.billing_stats.calls == [[PERSONAL_BILLING.id]]
    item = response.json()["items"][0]
    assert item["current_bill"] == {
        "total_amount": 110000,
        "status": "sent",
        "reference_month": "2026-07",
        "due_date": "2026-07-10",
    }
    assert item["pix_needs_setup"] is True


def test_login_list_filters_stale_organization_membership(billing_harness: BillingHarness) -> None:
    billing_harness.services.organization.members.pop((ORGANIZATION.id, USER.id))

    response = billing_harness.request("GET", "/api/v1/billings")

    assert response.status_code == 200
    assert [item["uuid"] for item in response.json()["items"]] == [PERSONAL_BILLING.uuid]


def test_list_skips_unsaved_rows_and_represents_missing_current_bill(billing_harness: BillingHarness) -> None:
    billing_harness.services.billing.billings.insert(0, Billing(name="Unsaved"))
    billing_harness.services.billing_stats.include_current = False

    response = billing_harness.request("GET", "/api/v1/billings", credential=INTEGRATION_SECRET)

    assert response.status_code == 200
    assert [item["uuid"] for item in response.json()["items"]] == [PERSONAL_BILLING.uuid]
    assert response.json()["items"][0]["current_bill"] is None


def test_billing_detail_returns_forms_and_server_capabilities(billing_harness: BillingHarness) -> None:
    response = billing_harness.request("GET", f"/api/v1/billings/{PERSONAL_BILLING.uuid}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["uuid"] == PERSONAL_BILLING.uuid
    assert payload["owner"] == {"type": "user", "uuid": None, "name": None}
    assert payload["items"] == [{"description": "Aluguel", "amount": 285000, "item_type": "fixed"}]
    assert payload["recipients"][0]["email"] == "joao@example.com"
    assert payload["reply_to"][0]["email"] == "joao@example.com"
    assert payload["capabilities"] == {
        "can_edit": True,
        "can_manage_bills": True,
        "can_delete": True,
        "can_transfer": True,
    }
    assert {template["comm_type"] for template in payload["communication_templates"]} == {
        "bill_ready",
        "payment_receipt",
    }
    assert "id" not in payload
    assert "owner_id" not in payload


def test_billing_detail_hides_resources_outside_grant(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "GET",
        f"/api/v1/billings/{ORG_BILLING.uuid}",
        credential=INTEGRATION_SECRET,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_create_personal_billing_normalizes_once_and_omits_child_replacement(
    billing_harness: BillingHarness,
) -> None:
    response = billing_harness.request("POST", "/api/v1/billings", json=_billing_payload())

    assert response.status_code == 201
    assert response.headers["x-rentivo-analytics-event"] == "rentivo_billing_created"
    call = billing_harness.services.billing.create_calls[0]
    assert call["name"] == "Apartamento novo"
    assert call["description"] == "Contrato anual"
    assert [(item.description, item.amount, item.item_type) for item in call["items"]] == [
        ("Aluguel", 300000, ItemType.FIXED),
        ("Agua", 0, ItemType.VARIABLE),
    ]
    assert call["owner_type"] == "user"
    assert call["owner_id"] == USER.id
    assert billing_harness.services.recipient.replace_calls == []
    assert billing_harness.services.reply_to.replace_calls == []
    assert _audit_events(billing_harness) == [AuditEventType.BILLING_CREATE]


def test_create_billing_explicit_children_are_replaced_and_audited(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "POST",
        "/api/v1/billings",
        json=_billing_payload(
            recipients=[{"name": "  Ana  ", "email": "  ana@example.com  "}],
            reply_to=[{"name": "  Financeiro  ", "email": "  financeiro@example.com  "}],
        ),
    )

    assert response.status_code == 201
    assert billing_harness.services.recipient.replace_calls == [(101, [{"name": "Ana", "email": "ana@example.com"}])]
    assert billing_harness.services.reply_to.replace_calls == [
        (101, [{"name": "Financeiro", "email": "financeiro@example.com"}])
    ]
    assert _audit_events(billing_harness) == [
        AuditEventType.BILLING_CREATE,
        AuditEventType.BILLING_RECIPIENTS_UPDATED,
        AuditEventType.BILLING_REPLY_TO_UPDATED,
    ]


def test_create_org_billing_requires_live_membership_and_admin_role(billing_harness: BillingHarness) -> None:
    billing_harness.services.organization.members[(ORGANIZATION.id, USER.id)].role = "manager"

    response = billing_harness.request(
        "POST",
        "/api/v1/billings",
        json=_billing_payload(owner={"type": "organization", "uuid": ORGANIZATION.uuid}),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_role"
    assert billing_harness.services.billing.create_calls == []


def test_create_org_billing_rejects_missing_live_membership_as_not_found(
    billing_harness: BillingHarness,
) -> None:
    billing_harness.services.organization.members.pop((ORGANIZATION.id, USER.id))

    response = billing_harness.request(
        "POST",
        "/api/v1/billings",
        json=_billing_payload(owner={"type": "organization", "uuid": ORGANIZATION.uuid}),
    )

    assert response.status_code == 404
    assert billing_harness.services.billing.create_calls == []


def test_create_org_billing_uses_granted_live_admin_workspace(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "POST",
        "/api/v1/billings",
        credential=ORG_ONLY_SECRET,
        json=_billing_payload(owner={"type": "organization", "uuid": ORGANIZATION.uuid}),
    )

    assert response.status_code == 201
    call = billing_harness.services.billing.create_calls[0]
    assert (call["owner_type"], call["owner_id"]) == ("organization", ORGANIZATION.id)
    assert response.json()["owner"] == {
        "type": "organization",
        "uuid": ORGANIZATION.uuid,
        "name": ORGANIZATION.name,
    }


@pytest.mark.parametrize(
    "payload",
    [
        _billing_payload(name="   "),
        _billing_payload(items=[]),
        _billing_payload(items=[{"description": "Aluguel", "amount": -1, "item_type": "fixed"}]),
        _billing_payload(items=[{"description": "Agua", "amount": 1, "item_type": "variable"}]),
        _billing_payload(owner={"type": "organization", "uuid": None}),
        _billing_payload(owner={"type": "user", "uuid": ORGANIZATION.uuid}),
        _billing_payload(recipients=[{"name": "Ana", "email": "invalid email"}]),
    ],
)
def test_create_rejects_invalid_billing_contract(payload: dict[str, Any], billing_harness: BillingHarness) -> None:
    response = billing_harness.request("POST", "/api/v1/billings", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert billing_harness.services.billing.create_calls == []


def test_create_maps_pix_validation_to_field_problem(billing_harness: BillingHarness) -> None:
    billing_harness.services.billing.create_error = ValueError("Chave PIX invalida")

    response = billing_harness.request(
        "POST",
        "/api/v1/billings",
        json=_billing_payload(pix_key="invalid"),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_billing"
    assert response.json()["fields"] == {"pix_key": "Chave PIX invalida"}


def test_create_org_billing_hides_unknown_organization(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "POST",
        "/api/v1/billings",
        json=_billing_payload(owner={"type": "organization", "uuid": "unknown-org"}),
    )

    assert response.status_code == 404


def test_create_org_billing_defensively_rechecks_membership_after_grant(
    billing_harness: BillingHarness,
) -> None:
    billing_harness.services.organization.members.pop((ORGANIZATION.id, USER.id))
    billing_harness.services.api_key.can_access_resource = lambda *_args: True

    response = billing_harness.request(
        "POST",
        "/api/v1/billings",
        json=_billing_payload(owner={"type": "organization", "uuid": ORGANIZATION.uuid}),
    )

    assert response.status_code == 404


def test_cookie_mutation_requires_csrf_but_bearer_does_not(billing_harness: BillingHarness) -> None:
    cookie_response = billing_harness.request(
        "POST",
        "/api/v1/billings",
        json=_billing_payload(),
        csrf=False,
    )
    bearer_response = billing_harness.request(
        "POST",
        "/api/v1/billings",
        credential=INTEGRATION_SECRET,
        json=_billing_payload(),
    )

    assert cookie_response.status_code == 403
    assert cookie_response.json()["code"] == "csrf_failed"
    assert bearer_response.status_code == 201


def test_patch_omits_encrypted_children_and_preserves_existing_rows(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "PATCH",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}",
        json={"name": "  Nome atualizado  "},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Nome atualizado"
    assert billing_harness.services.recipient.replace_calls == []
    assert billing_harness.services.reply_to.replace_calls == []
    assert _audit_events(billing_harness) == [AuditEventType.BILLING_UPDATE]


def test_patch_explicit_empty_children_clears_and_audits(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "PATCH",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}",
        json={"recipients": [], "reply_to": []},
    )

    assert response.status_code == 200
    assert billing_harness.services.recipient.replace_calls == [(PERSONAL_BILLING.id, [])]
    assert billing_harness.services.reply_to.replace_calls == [(PERSONAL_BILLING.id, [])]
    assert _audit_events(billing_harness) == [
        AuditEventType.BILLING_UPDATE,
        AuditEventType.BILLING_RECIPIENTS_UPDATED,
        AuditEventType.BILLING_REPLY_TO_UPDATED,
    ]


def test_patch_explicit_items_replaces_template_lines(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "PATCH",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}",
        json={"items": [{"description": "Novo aluguel", "amount": 310000, "item_type": "fixed"}]},
    )

    assert response.status_code == 200
    assert [(item.description, item.amount) for item in billing_harness.services.billing.update_calls[0].items] == [
        ("Novo aluguel", 310000)
    ]


def test_patch_rejects_manager_and_preserves_billing(billing_harness: BillingHarness) -> None:
    billing_harness.services.authorization.role_overrides[PERSONAL_BILLING.id] = "manager"

    response = billing_harness.request(
        "PATCH",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}",
        json={"name": "Nao permitido"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_role"
    assert billing_harness.services.billing.update_calls == []


def test_patch_maps_service_validation_without_replacing_children(billing_harness: BillingHarness) -> None:
    billing_harness.services.billing.update_error = ValueError("PIX invalido")

    response = billing_harness.request(
        "PATCH",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}",
        json={"pix_key": "invalid", "recipients": []},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_billing"
    assert billing_harness.services.recipient.replace_calls == []


def test_put_recipients_and_reply_to_replace_scoped_children(billing_harness: BillingHarness) -> None:
    recipients = billing_harness.request(
        "PUT",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/recipients",
        json={"items": [{"name": " Ana ", "email": " ana@example.com "}]},
    )
    reply_to = billing_harness.request(
        "PUT",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/reply-to",
        json={"items": []},
    )

    assert recipients.status_code == reply_to.status_code == 200
    assert recipients.json()["items"][0]["email"] == "ana@example.com"
    assert reply_to.json() == {"items": []}
    assert _audit_events(billing_harness) == [
        AuditEventType.BILLING_RECIPIENTS_UPDATED,
        AuditEventType.BILLING_REPLY_TO_UPDATED,
    ]


def test_delete_billing_is_role_scoped_and_preserves_cleanup_audit_order(
    billing_harness: BillingHarness,
) -> None:
    response = billing_harness.request("DELETE", f"/api/v1/billings/{PERSONAL_BILLING.uuid}")

    assert response.status_code == 204
    assert response.headers["x-rentivo-analytics-event"] == "rentivo_billing_deleted"
    assert billing_harness.services.storage_cleanup.billing_calls[0][1].id == PERSONAL_BILLING.id
    assert billing_harness.services.billing.delete_calls == [PERSONAL_BILLING.id]
    assert _audit_events(billing_harness) == [AuditEventType.BILLING_DELETE]


@pytest.mark.parametrize("role", ["manager", "viewer"])
def test_delete_billing_rejects_non_admin_roles(role: str, billing_harness: BillingHarness) -> None:
    billing_harness.services.authorization.role_overrides[PERSONAL_BILLING.id] = role

    response = billing_harness.request("DELETE", f"/api/v1/billings/{PERSONAL_BILLING.uuid}")

    assert response.status_code == 403
    assert billing_harness.services.billing.delete_calls == []


def test_transfer_requires_source_owner_and_live_destination_membership(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/transfer",
        json={"organization_uuid": ORGANIZATION.uuid},
    )

    assert response.status_code == 204
    assert billing_harness.services.billing.transfer_calls == [(PERSONAL_BILLING.id, ORGANIZATION.id)]
    assert billing_harness.services.billing_notification.calls[0]["actor_email"] == USER.email
    assert billing_harness.services.billing_notification.calls[0]["previous_owner"] == {
        "owner_type": "user",
        "owner_id": USER.id,
    }
    assert _audit_events(billing_harness) == [AuditEventType.BILLING_TRANSFER]


def test_transfer_rejects_ungranted_or_stale_destination_before_mutation(billing_harness: BillingHarness) -> None:
    billing_harness.services.organization.members.pop((ORGANIZATION.id, USER.id))

    response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/transfer",
        json={"organization_uuid": ORGANIZATION.uuid},
    )

    assert response.status_code == 404
    assert billing_harness.services.billing.transfer_calls == []


def test_transfer_rejects_organization_owned_source_and_service_conflict(
    billing_harness: BillingHarness,
) -> None:
    org_response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{ORG_BILLING.uuid}/transfer",
        json={"organization_uuid": ORGANIZATION.uuid},
    )
    billing_harness.services.billing.transfer_error = ValueError("ownership changed")
    conflict_response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/transfer",
        json={"organization_uuid": ORGANIZATION.uuid},
    )

    assert org_response.status_code == 403
    assert org_response.json()["code"] == "insufficient_role"
    assert conflict_response.status_code == 409
    assert conflict_response.json()["code"] == "billing_transfer_conflict"


def test_transfer_defensive_owner_and_destination_checks(billing_harness: BillingHarness) -> None:
    billing_harness.services.authorization.role_overrides[ORG_BILLING.id] = "owner"
    organization_owned = billing_harness.request(
        "POST",
        f"/api/v1/billings/{ORG_BILLING.uuid}/transfer",
        json={"organization_uuid": ORGANIZATION.uuid},
    )
    unknown_destination = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/transfer",
        json={"organization_uuid": "unknown-org"},
    )
    billing_harness.services.organization.members.pop((ORGANIZATION.id, USER.id))
    billing_harness.services.api_key.can_access_resource = lambda *_args: True
    stale_destination = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/transfer",
        json={"organization_uuid": ORGANIZATION.uuid},
    )

    assert organization_owned.status_code == 403
    assert unknown_destination.status_code == 404
    assert stale_destination.status_code == 404


def test_expense_collection_and_create_use_expense_scopes_and_centavos(billing_harness: BillingHarness) -> None:
    listed = billing_harness.request("GET", f"/api/v1/billings/{PERSONAL_BILLING.uuid}/expenses")
    created = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/expenses",
        json={
            "description": "  Seguro anual  ",
            "amount": 99_900,
            "category": "seguro",
            "incurred_on": "2026-07-18",
        },
    )

    assert listed.status_code == 200
    assert listed.json()["items"][0]["amount"] == 120000
    assert created.status_code == 201
    assert billing_harness.services.expense.create_calls == [
        {
            "billing_id": PERSONAL_BILLING.id,
            "description": "Seguro anual",
            "amount": 99900,
            "category": "seguro",
            "incurred_on": "2026-07-18",
        }
    ]
    assert _audit_events(billing_harness) == [AuditEventType.EXPENSE_CREATE]


@pytest.mark.parametrize(
    "payload",
    [
        {"description": "", "amount": 100, "category": "iptu", "incurred_on": "2026-07-18"},
        {"description": "X", "amount": 0, "category": "iptu", "incurred_on": "2026-07-18"},
        {"description": "X", "amount": 100, "category": "bogus", "incurred_on": "2026-07-18"},
        {"description": "X", "amount": 100, "category": "iptu", "incurred_on": "not-a-date"},
    ],
)
def test_create_expense_rejects_invalid_contract(payload: dict[str, Any], billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/expenses",
        json=payload,
    )

    assert response.status_code == 422
    assert billing_harness.services.expense.create_calls == []


def test_manager_can_mutate_expenses_but_viewer_cannot(billing_harness: BillingHarness) -> None:
    payload = {"description": "X", "amount": 100, "category": "iptu", "incurred_on": "2026-07-18"}
    billing_harness.services.authorization.role_overrides[PERSONAL_BILLING.id] = "manager"
    manager = billing_harness.request("POST", f"/api/v1/billings/{PERSONAL_BILLING.uuid}/expenses", json=payload)
    billing_harness.services.authorization.role_overrides[PERSONAL_BILLING.id] = "viewer"
    viewer = billing_harness.request("POST", f"/api/v1/billings/{PERSONAL_BILLING.uuid}/expenses", json=payload)

    assert manager.status_code == 201
    assert viewer.status_code == 403


def test_delete_expense_checks_parent_before_mutation(billing_harness: BillingHarness) -> None:
    mismatched = billing_harness.request(
        "DELETE",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/expenses/expense-foreign",
    )
    deleted = billing_harness.request(
        "DELETE",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/expenses/expense-personal",
    )

    assert mismatched.status_code == 404
    assert deleted.status_code == 204
    assert [expense.uuid for expense in billing_harness.services.expense.delete_calls] == ["expense-personal"]
    assert _audit_events(billing_harness) == [AuditEventType.EXPENSE_DELETE]


def test_attachment_collection_upload_and_metadata_never_expose_storage_key(
    billing_harness: BillingHarness,
) -> None:
    listed = billing_harness.request("GET", f"/api/v1/billings/{PERSONAL_BILLING.uuid}/attachments")
    uploaded = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/attachments",
        data={"name": "  Contrato novo  "},
        files={"file": ("novo.pdf", b"%PDF-new", "application/pdf")},
    )

    assert listed.status_code == 200
    assert listed.json()["items"][0]["uuid"] == "attachment-personal"
    assert "storage_key" not in listed.text
    assert uploaded.status_code == 201
    assert uploaded.headers["x-rentivo-analytics-event"] == "rentivo_billing_attachment_uploaded"
    assert billing_harness.services.billing_attachment.add_calls[0]["name"] == "Contrato novo"
    assert billing_harness.services.billing_attachment.add_calls[0]["file_bytes"] == b"%PDF-new"
    assert "private/created.pdf" not in uploaded.text
    assert _audit_events(billing_harness) == [AuditEventType.ATTACHMENT_UPLOAD]


def test_attachment_upload_maps_service_validation_to_file_problem(billing_harness: BillingHarness) -> None:
    billing_harness.services.billing_attachment.add_error = ValueError("Unsupported file type")

    response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/attachments",
        data={"name": "Arquivo"},
        files={"file": ("arquivo.gif", b"GIF89a", "image/gif")},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_attachment"
    assert response.json()["fields"] == {"file": "Unsupported file type"}


def test_attachment_upload_requires_a_named_file(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/attachments",
        data={"name": "Arquivo"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_attachment"


def test_attachment_download_checks_parent_before_storage_resolution(billing_harness: BillingHarness) -> None:
    mismatch = billing_harness.request(
        "GET",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/attachments/attachment-foreign",
    )
    local = billing_harness.request(
        "GET",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/attachments/attachment-personal",
    )

    assert mismatch.status_code == 404
    assert [attachment.uuid for attachment in billing_harness.services.billing_attachment.ref_calls] == [
        "attachment-personal"
    ]
    assert local.status_code == 200
    assert local.content == b"%PDF-test"
    assert local.headers["content-type"] == "application/pdf"


def test_attachment_download_redirects_url_refs(billing_harness: BillingHarness) -> None:
    billing_harness.services.billing_attachment.ref = FileRef(
        kind="url", location="https://storage.example.test/attachment"
    )

    response = billing_harness.request(
        "GET",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/attachments/attachment-personal",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "https://storage.example.test/attachment"


def test_attachment_delete_is_parent_scoped_and_enqueues_cleanup(billing_harness: BillingHarness) -> None:
    mismatch = billing_harness.request(
        "DELETE",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/attachments/attachment-foreign",
    )
    deleted = billing_harness.request(
        "DELETE",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/attachments/attachment-personal",
    )

    assert mismatch.status_code == 404
    assert deleted.status_code == 204
    assert [attachment.uuid for attachment in billing_harness.services.billing_attachment.delete_calls] == [
        "attachment-personal"
    ]
    assert billing_harness.services.storage_cleanup.attachment_calls[0][1].uuid == "attachment-personal"
    assert _audit_events(billing_harness) == [AuditEventType.ATTACHMENT_DELETE]


def test_export_enqueues_for_requesting_principal_and_audits(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/exports",
        credential=INTEGRATION_SECRET,
        json={"format": "xlsx"},
    )

    assert response.status_code == 202
    assert response.json() == {"status": "queued", "format": "xlsx"}
    actor, job_type, payload = billing_harness.services.job.calls[0]
    assert actor.source == "integration"
    assert job_type == "export.generate"
    assert payload == {
        "billing_id": PERSONAL_BILLING.id,
        "format": "xlsx",
        "requested_by_user_id": USER.id,
    }
    assert _audit_events(billing_harness) == [AuditEventType.BILLING_EXPORT]


def test_export_rejects_unknown_format(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/exports",
        json={"format": "pdf"},
    )

    assert response.status_code == 422
    assert billing_harness.services.job.calls == []


def test_communication_preview_renders_safe_html_and_moderation(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/communications/preview",
        json={"subject": "Aviso", "body": "Que merda, **pague** <script>alert(1)</script>"},
    )

    assert response.status_code == 200
    assert response.json()["mild"] == ["merda"]
    assert response.json()["severe"] == []
    assert "<strong>pague</strong>" in response.json()["html"]
    assert "<script>" not in response.json()["html"]


def _communication_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "bill_uuid": PERSONAL_BILL.uuid,
        "comm_type": "bill_ready",
        "subject": "  Cobranca {{unidade}}  ",
        "body": "  Prezado {{nome_inquilino}}  ",
        "recipient_uuids": ["recipient-existing"],
        "acknowledge_warning": False,
        "save_scope": None,
    }
    payload.update(overrides)
    return payload


def test_communication_send_is_parent_scoped_fans_out_and_audits(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/communications/send",
        json=_communication_payload(save_scope="billing"),
    )

    assert response.status_code == 202
    assert response.json() == {"queued_count": 1}
    call = billing_harness.services.communication.send_calls[0]
    assert call["bill"].uuid == PERSONAL_BILL.uuid
    assert call["recipients"][0].uuid == "recipient-existing"
    assert call["subject_template"] == "Cobranca {{unidade}}"
    assert call["body_template"] == "Prezado {{nome_inquilino}}"
    assert billing_harness.services.communication.save_calls == [
        ("billing", PERSONAL_BILLING.id, "bill_ready", "Cobranca {{unidade}}", "Prezado {{nome_inquilino}}")
    ]
    assert _audit_events(billing_harness) == [
        AuditEventType.COMMUNICATION_TEMPLATE_SAVED,
        AuditEventType.COMMUNICATION_SENT,
    ]


def test_communication_send_checks_bill_parent_and_selected_recipients(billing_harness: BillingHarness) -> None:
    foreign_bill = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/communications/send",
        json=_communication_payload(bill_uuid=FOREIGN_BILL.uuid),
    )
    foreign_recipient = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/communications/send",
        json=_communication_payload(recipient_uuids=["reply-existing"]),
    )

    assert foreign_bill.status_code == 404
    assert foreign_recipient.status_code == 422
    assert foreign_recipient.json()["code"] == "invalid_recipients"
    assert billing_harness.services.communication.send_calls == []


def test_communication_owner_template_is_forbidden_to_manager_before_send(
    billing_harness: BillingHarness,
) -> None:
    billing_harness.services.authorization.role_overrides[PERSONAL_BILLING.id] = "manager"

    response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/communications/send",
        json=_communication_payload(save_scope="owner"),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_role"
    assert billing_harness.services.communication.send_calls == []


def test_communication_owner_template_saves_for_personal_owner(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/communications/send",
        json=_communication_payload(save_scope="owner"),
    )

    assert response.status_code == 202
    assert billing_harness.services.communication.save_calls == [
        ("user", USER.id, "bill_ready", "Cobranca {{unidade}}", "Prezado {{nome_inquilino}}")
    ]


def test_communication_send_rejects_duplicate_recipient_selection(billing_harness: BillingHarness) -> None:
    response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/communications/send",
        json=_communication_payload(recipient_uuids=["recipient-existing", "recipient-existing"]),
    )

    assert response.status_code == 422
    assert billing_harness.services.communication.send_calls == []


def test_communication_severe_is_blocked_and_mild_requires_acknowledgement(
    billing_harness: BillingHarness,
) -> None:
    severe = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/communications/send",
        json=_communication_payload(body="Se nao pagar vou te matar."),
    )
    mild = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/communications/send",
        json=_communication_payload(body="Que merda, pague."),
    )

    assert severe.status_code == 422
    assert severe.json()["code"] == "communication_blocked"
    assert mild.status_code == 422
    assert mild.json()["code"] == "communication_warning_unacknowledged"
    assert billing_harness.services.communication.send_calls == []
    assert _audit_events(billing_harness) == [AuditEventType.COMMUNICATION_BLOCKED]


def test_communication_mild_acknowledgement_sends_and_audits_override(
    billing_harness: BillingHarness,
) -> None:
    response = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/communications/send",
        json=_communication_payload(body="Que merda, pague.", acknowledge_warning=True),
    )

    assert response.status_code == 202
    assert _audit_events(billing_harness) == [
        AuditEventType.COMMUNICATION_SENT,
        AuditEventType.COMMUNICATION_FLAGGED_OVERRIDE,
    ]


def test_communication_send_requires_the_selected_document(billing_harness: BillingHarness) -> None:
    PERSONAL_BILL_VALUE = billing_harness.services.bill.get_bill_by_uuid(PERSONAL_BILL.uuid)
    assert PERSONAL_BILL_VALUE is not None
    PERSONAL_BILL_VALUE.pdf_path = None
    invoice = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/communications/send",
        json=_communication_payload(),
    )
    PERSONAL_BILL_VALUE.recibo_pdf_path = None
    receipt = billing_harness.request(
        "POST",
        f"/api/v1/billings/{PERSONAL_BILLING.uuid}/communications/send",
        json=_communication_payload(comm_type="payment_receipt"),
    )

    assert invoice.status_code == 409
    assert invoice.json()["code"] == "invoice_unavailable"
    assert receipt.status_code == 409
    assert receipt.json()["code"] == "receipt_unavailable"


@pytest.mark.parametrize(
    ("scope", "method", "path", "kwargs"),
    [
        (APIScope.BILLINGS_READ, "GET", "/api/v1/billings", {}),
        (
            APIScope.BILLINGS_WRITE,
            "PATCH",
            f"/api/v1/billings/{PERSONAL_BILLING.uuid}",
            {"json": {"name": "X"}},
        ),
        (APIScope.EXPENSES_READ, "GET", f"/api/v1/billings/{PERSONAL_BILLING.uuid}/expenses", {}),
        (
            APIScope.EXPENSES_WRITE,
            "POST",
            f"/api/v1/billings/{PERSONAL_BILLING.uuid}/expenses",
            {
                "json": {
                    "description": "X",
                    "amount": 100,
                    "category": "iptu",
                    "incurred_on": "2026-07-18",
                }
            },
        ),
        (APIScope.FILES_READ, "GET", f"/api/v1/billings/{PERSONAL_BILLING.uuid}/attachments", {}),
        (
            APIScope.FILES_WRITE,
            "POST",
            f"/api/v1/billings/{PERSONAL_BILLING.uuid}/attachments",
            {"data": {"name": "X"}, "files": {"file": ("x.pdf", b"%PDF", "application/pdf")}},
        ),
        (
            APIScope.EXPORTS_CREATE,
            "POST",
            f"/api/v1/billings/{PERSONAL_BILLING.uuid}/exports",
            {"json": {"format": "csv"}},
        ),
        (
            APIScope.COMMUNICATIONS_READ,
            "POST",
            f"/api/v1/billings/{PERSONAL_BILLING.uuid}/communications/preview",
            {"json": {"subject": "S", "body": "B"}},
        ),
        (
            APIScope.COMMUNICATIONS_SEND,
            "POST",
            f"/api/v1/billings/{PERSONAL_BILLING.uuid}/communications/send",
            {"json": _communication_payload()},
        ),
    ],
)
def test_each_domain_operation_requires_its_corresponding_scope(
    scope: APIScope,
    method: str,
    path: str,
    kwargs: dict[str, Any],
    billing_harness: BillingHarness,
) -> None:
    key = NO_SCOPE_KEY.model_copy(update={"scopes": ALL_FIRST_PARTY_SCOPES - {scope.value}})
    billing_harness.services.api_key.credentials[NO_SCOPE_SECRET] = key

    response = billing_harness.request(method, path, credential=NO_SCOPE_SECRET, **kwargs)

    assert response.status_code == 403
    assert response.json()["code"] == "missing_scope"


def test_billings_openapi_contract_is_complete_typed_and_strict(billing_harness: BillingHarness) -> None:
    schema = billing_harness.app.openapi()
    expected_paths = {
        "/api/v1/billings",
        "/api/v1/billings/{billing_uuid}",
        "/api/v1/billings/{billing_uuid}/transfer",
        "/api/v1/billings/{billing_uuid}/recipients",
        "/api/v1/billings/{billing_uuid}/reply-to",
        "/api/v1/billings/{billing_uuid}/expenses",
        "/api/v1/billings/{billing_uuid}/expenses/{expense_uuid}",
        "/api/v1/billings/{billing_uuid}/attachments",
        "/api/v1/billings/{billing_uuid}/attachments/{attachment_uuid}",
        "/api/v1/billings/{billing_uuid}/exports",
        "/api/v1/billings/{billing_uuid}/communications/preview",
        "/api/v1/billings/{billing_uuid}/communications/send",
    }
    paths = {path for path in schema["paths"] if path.startswith("/api/v1/billings")}

    assert paths == expected_paths
    assert set(schema["paths"]["/api/v1/billings"]) == {"get", "post"}
    assert set(schema["paths"]["/api/v1/billings/{billing_uuid}"]) == {"get", "patch", "delete"}
    for model_name in (
        "BillingCreateRequest",
        "BillingUpdateRequest",
        "ExpenseCreateRequest",
        "CommunicationSendRequest",
    ):
        assert schema["components"]["schemas"][model_name]["additionalProperties"] is False
