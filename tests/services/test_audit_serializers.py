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
            paid_at=now,
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
        assert result["paid_at"] == now.isoformat()
        assert result["created_at"] == now.isoformat()

    def test_bill_none_paid_at(self):
        bill = Bill(billing_id=1, reference_month="2026-01", total_amount=0)
        result = serialize_bill(bill)
        assert result["paid_at"] is None
        assert result["created_at"] is None


class TestSerializeUser:
    def test_excludes_password_hash(self):
        now = datetime(2026, 1, 1, 0, 0, 0)
        user = User(
            id=1,
            username="admin",
            email="admin@test.com",
            password_hash="$2b$12$secrethash",
            created_at=now,
        )
        result = serialize_user(user)

        assert result["id"] == 1
        assert result["username"] == "admin"
        assert result["email"] == "admin@test.com"
        assert result["created_at"] == now.isoformat()
        assert "password_hash" not in result

    def test_user_none_created_at(self):
        user = User(username="test", password_hash="hash")
        result = serialize_user(user)
        assert result["created_at"] is None


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
            invited_username="bob",
            invited_by_user_id=1,
            invited_by_username="alice",
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
        assert result["invited_username"] == "bob"
        assert result["invited_by_user_id"] == 1
        assert result["invited_by_username"] == "alice"
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
