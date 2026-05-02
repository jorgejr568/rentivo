from datetime import datetime

from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import Billing, BillingItem, ItemType
from rentivo.models.invite import Invite
from rentivo.models.organization import Organization
from rentivo.models.user import User
from rentivo.services.audit_serializers import (
    serialize_bill,
    serialize_billing,
    serialize_invite,
    serialize_organization,
    serialize_user,
)


class TestSerializeBilling:
    def test_basic_billing(self):
        now = datetime(2026, 1, 15, 10, 0, 0)
        billing = Billing(
            id=1,
            uuid="abc123",
            name="Apt 101",
            description="Monthly",
            pix_key="pix@test.com",
            owner_type="user",
            owner_id=5,
            items=[
                BillingItem(
                    id=10,
                    description="Rent",
                    amount=285000,
                    item_type=ItemType.FIXED,
                    sort_order=0,
                ),
                BillingItem(
                    id=11,
                    description="Water",
                    amount=0,
                    item_type=ItemType.VARIABLE,
                    sort_order=1,
                ),
            ],
            created_at=now,
            updated_at=now,
        )
        result = serialize_billing(billing)

        assert result["id"] == 1
        assert result["uuid"] == "abc123"
        assert result["name"] == "Apt 101"
        assert result["description"] == "Monthly"
        assert result["pix_key"] == "pix@test.com"
        assert result["owner_type"] == "user"
        assert result["owner_id"] == 5
        assert len(result["items"]) == 2
        assert result["items"][0]["description"] == "Rent"
        assert result["items"][0]["amount"] == 285000
        assert result["items"][0]["item_type"] == "fixed"
        assert result["items"][1]["item_type"] == "variable"
        assert result["created_at"] == now.isoformat()
        assert result["updated_at"] == now.isoformat()

    def test_billing_empty_items(self):
        billing = Billing(id=1, name="Empty", items=[])
        result = serialize_billing(billing)
        assert result["items"] == []

    def test_billing_none_dates(self):
        billing = Billing(name="No dates")
        result = serialize_billing(billing)
        assert result["created_at"] is None
        assert result["updated_at"] is None


class TestSerializeBill:
    def test_basic_bill(self):
        now = datetime(2026, 2, 1, 14, 30, 0)
        bill = Bill(
            id=5,
            uuid="bill123",
            billing_id=1,
            reference_month="2026-02",
            total_amount=295000,
            line_items=[
                BillLineItem(
                    id=20,
                    description="Rent",
                    amount=285000,
                    item_type=ItemType.FIXED,
                    sort_order=0,
                ),
            ],
            pdf_path="abc/def.pdf",
            notes="Test note",
            due_date="10/03/2026",
            status="paid",
            status_updated_at=now,
            created_at=now,
        )
        result = serialize_bill(bill)

        assert result["id"] == 5
        assert result["uuid"] == "bill123"
        assert result["billing_id"] == 1
        assert result["reference_month"] == "2026-02"
        assert result["total_amount"] == 295000
        assert len(result["line_items"]) == 1
        assert result["line_items"][0]["description"] == "Rent"
        assert result["line_items"][0]["item_type"] == "fixed"
        assert result["pdf_path"] == "abc/def.pdf"
        assert result["notes"] == "Test note"
        assert result["due_date"] == "10/03/2026"
        assert result["status"] == "paid"
        assert result["status_updated_at"] == now.isoformat()
        assert result["created_at"] == now.isoformat()

    def test_bill_none_status_updated_at(self):
        bill = Bill(billing_id=1, reference_month="2026-01", total_amount=0)
        result = serialize_bill(bill)
        assert result["status"] == "draft"
        assert result["status_updated_at"] is None
        assert result["created_at"] is None


class TestSerializeUser:
    def test_excludes_password_hash(self):
        now = datetime(2026, 1, 1, 0, 0, 0)
        user = User(
            id=1,
            email="admin@test.com",
            password_hash="$2b$12$secrethash",
            created_at=now,
        )
        result = serialize_user(user)

        assert result["id"] == 1
        assert result["email"] == "admin@test.com"
        assert result["created_at"] == now.isoformat()
        assert "password_hash" not in result
        assert "username" not in result

    def test_user_none_created_at(self):
        user = User(email="test@test.com", password_hash="hash")
        result = serialize_user(user)
        assert result["created_at"] is None


def test_serialize_user_uses_email():
    user = User(id=1, email="a@b.com", password_hash="x", pix_key="k")
    result = serialize_user(user)
    assert result["email"] == "a@b.com"
    assert "username" not in result
    assert "password_hash" not in result


class TestSerializeOrganization:
    def test_basic_org(self):
        now = datetime(2026, 1, 15)
        org = Organization(
            id=1,
            uuid="org123",
            name="My Org",
            created_by=5,
            created_at=now,
            updated_at=now,
        )
        result = serialize_organization(org)

        assert result["id"] == 1
        assert result["uuid"] == "org123"
        assert result["name"] == "My Org"
        assert result["created_by"] == 5
        assert result["created_at"] == now.isoformat()
        assert result["updated_at"] == now.isoformat()

    def test_org_none_dates(self):
        org = Organization(name="No dates")
        result = serialize_organization(org)
        assert result["created_at"] is None
        assert result["updated_at"] is None


class TestSerializeInvite:
    def test_basic_invite(self):
        now = datetime(2026, 2, 10, 8, 0, 0)
        invite = Invite(
            id=1,
            uuid="inv123",
            organization_id=3,
            organization_name="Org A",
            invited_user_id=5,
            invited_email="bob",
            invited_by_user_id=1,
            invited_by_email="alice",
            role="viewer",
            status="pending",
            created_at=now,
            responded_at=None,
        )
        result = serialize_invite(invite)

        assert result["id"] == 1
        assert result["uuid"] == "inv123"
        assert result["organization_id"] == 3
        assert result["organization_name"] == "Org A"
        assert result["invited_user_id"] == 5
        assert result["invited_email"] == "bob"
        assert result["invited_by_user_id"] == 1
        assert result["invited_by_email"] == "alice"
        assert result["role"] == "viewer"
        assert result["status"] == "pending"
        assert result["created_at"] == now.isoformat()
        assert result["responded_at"] is None

    def test_invite_with_responded_at(self):
        now = datetime(2026, 2, 10, 8, 0, 0)
        invite = Invite(
            organization_id=1,
            invited_user_id=2,
            invited_by_user_id=3,
            status="accepted",
            responded_at=now,
        )
        result = serialize_invite(invite)
        assert result["responded_at"] == now.isoformat()


class TestSerializeJobPayload:
    def test_email_send_keeps_event_and_to_email_drops_ctx_values(self):
        from rentivo.services.audit_serializers import serialize_job_payload

        result = serialize_job_payload(
            {
                "job_type": "email.send",
                "event": "welcome",
                "to_email": "alice@example.com",
                "ctx": {"email": "alice@example.com", "pix_setup_url": "http://x/pix"},
            }
        )

        assert result["event"] == "welcome"
        assert result["to_email"] == "alice@example.com"
        assert result["ctx_keys_count"] == 2
        assert "ctx" not in result  # raw ctx values stripped
        assert "pix_setup_url" not in result

    def test_strips_disallowed_keys(self):
        from rentivo.services.audit_serializers import serialize_job_payload

        result = serialize_job_payload(
            {
                "job_type": "email.send",
                "event": "password_reset",
                "to_email": "alice@example.com",
                "ctx": {"reset_url": "http://x/r"},
                "password": "hunter2",
                "auth_token": "deadbeef",
                "secret_key": "shh",
                "pix_key": "alice@bank",
                "pix_merchant_name": "Alice",
            }
        )

        for stripped in ("password", "auth_token", "secret_key", "pix_key", "pix_merchant_name"):
            assert stripped not in result

    def test_unknown_job_type_keeps_only_keys_index(self):
        from rentivo.services.audit_serializers import serialize_job_payload

        result = serialize_job_payload({"job_type": "pdf.render", "bill_id": 7, "force": True})

        assert result == {"job_type": "pdf.render", "keys": ["bill_id", "force", "job_type"]}

    def test_unknown_job_type_strips_disallowed_keys_from_index(self):
        from rentivo.services.audit_serializers import serialize_job_payload

        result = serialize_job_payload(
            {
                "job_type": "pdf.render",
                "bill_id": 7,
                "password": "secret",
                "auth_token": "deadbeef",
                "secret_key": "shh",
                "pix_key": "alice@bank",
                "pix_merchant_name": "Alice",
                "pix_merchant_city": "SP",
            }
        )

        assert result == {"job_type": "pdf.render", "keys": ["bill_id", "job_type"]}

    def test_missing_job_type_falls_through_to_unknown_branch(self):
        from rentivo.services.audit_serializers import serialize_job_payload

        result = serialize_job_payload({"foo": "bar"})

        assert result == {"job_type": "", "keys": ["foo"]}
