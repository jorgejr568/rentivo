from datetime import datetime

from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import Billing, BillingItem, ItemType
from rentivo.models.invite import Invite
from rentivo.models.organization import Organization
from rentivo.models.theme import Theme
from rentivo.models.user import User
from rentivo.services.audit_serializers import (
    serialize_bill,
    serialize_billing,
    serialize_invite,
    serialize_job_payload,
    serialize_organization,
    serialize_theme,
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
        # PIX redaction: short non-empty values collapse to '***'.
        # The Billing in this test has pix_key="pix@test.com" (12 chars) and
        # empty merchant fields.
        assert result["pix_key"] == "pix...om"  # 'pix@test.com' → first 3 + ... + last 2
        assert result["pix_merchant_name"] == ""  # empty → empty
        assert result["pix_merchant_city"] == ""
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
        assert result["email"] == "ad...@test.com"  # email is redacted
        assert result["created_at"] == now.isoformat()
        assert "password_hash" not in result
        assert "username" not in result

    def test_user_none_created_at(self):
        user = User(email="test@test.com", password_hash="hash")
        result = serialize_user(user)
        assert result["created_at"] is None

    def test_pix_redacted_to_partial_mask(self):
        user = User(
            email="alice@example.com",
            password_hash="x",
            pix_key="alice@pix.com",
            pix_merchant_name="Alice da Silva",
            pix_merchant_city="Sao Paulo",
        )
        result = serialize_user(user)

        # All PIX fields use the PIX mask (first 3 + '...' + last 2).
        assert result["pix_key"] == "ali...om"  # 'alice@pix.com' (13 chars)
        assert result["pix_merchant_name"] == "Ali...va"  # 'Alice da Silva' (14 chars)
        assert result["pix_merchant_city"] == "Sao...lo"  # 'Sao Paulo' (9 chars)

        # Plaintext, *_set, and *_hash forms are all gone.
        for prefix_key in ("pix_key", "pix_merchant_name", "pix_merchant_city"):
            assert f"{prefix_key}_set" not in result
            assert f"{prefix_key}_hash" not in result

    def test_pix_unset_yields_empty_strings(self):
        user = User(email="bob@example.com", password_hash="x")  # no PIX
        result = serialize_user(user)

        assert result["pix_key"] == ""
        assert result["pix_merchant_name"] == ""
        assert result["pix_merchant_city"] == ""

    def test_pix_short_value_collapses_to_stars(self):
        # Less than 6 chars can't be partial-masked without exposing the value.
        user = User(email="x@x", password_hash="x", pix_key="Eve")  # 3 chars
        result = serialize_user(user)
        assert result["pix_key"] == "***"

    def test_pix_redaction_is_deterministic(self):
        """Same plaintext → same redacted form. Identity follows from the
        function being key-less and pure; no settings dependency."""
        a = serialize_user(User(email="a@x", password_hash="x", pix_key="alice@pix.com"))
        b = serialize_user(User(email="b@x", password_hash="x", pix_key="alice@pix.com"))
        c = serialize_user(User(email="c@x", password_hash="x", pix_key="bob@pix.com"))

        assert a["pix_key"] == b["pix_key"] == "ali...om"
        assert a["pix_key"] != c["pix_key"]

    def test_email_redacted_to_partial_mask(self):
        user = User(
            id=1,
            email="alice@example.com",
            password_hash="hash",
            pix_key="",
            pix_merchant_name="",
            pix_merchant_city="",
        )
        result = serialize_user(user)
        # Partial-mask: first 2 chars of local + ...@ + full domain.
        assert result["email"] == "al...@example.com"
        # password_hash must NEVER appear.
        assert "password_hash" not in result

    def test_email_redaction_is_deterministic(self):
        """Same plaintext email → same redacted form."""
        a = serialize_user(User(email="alice@example.com", password_hash="x"))
        b = serialize_user(User(email="bob@example.com", password_hash="x"))
        c = serialize_user(User(email="alice@example.com", password_hash="y"))

        assert a["email"] == c["email"] == "al...@example.com"
        assert a["email"] != b["email"]

    def test_email_short_local_collapses_to_stars(self):
        # Email with 1-char local part can't be partial-masked.
        user = User(email="a@example.com", password_hash="x")
        result = serialize_user(user)
        assert result["email"] == "***@example.com"

    def test_email_empty_serializes_to_empty(self):
        """Empty email round-trips as empty — redact() returns "" on empty input."""
        user = User(
            id=1,
            email="",
            password_hash="x",
            pix_key="",
            pix_merchant_name="",
            pix_merchant_city="",
        )
        result = serialize_user(user)
        assert result["email"] == ""


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
        # The org in this test has no PIX configured.
        assert result["pix_key"] == ""
        assert result["pix_merchant_name"] == ""
        assert result["pix_merchant_city"] == ""
        for prefix_key in ("pix_key", "pix_merchant_name", "pix_merchant_city"):
            assert f"{prefix_key}_set" not in result
            assert f"{prefix_key}_hash" not in result

    def test_org_none_dates(self):
        org = Organization(name="No dates")
        result = serialize_organization(org)
        assert result["created_at"] is None
        assert result["updated_at"] is None

    def test_pix_redacted_to_partial_mask_when_configured(self):
        now = datetime(2026, 1, 15)
        org = Organization(
            id=1,
            uuid="org123",
            name="Acme",
            created_by=5,
            pix_key="12345678000190",  # 14-char CNPJ
            pix_merchant_name="Acme Imobiliaria",  # 16 chars
            pix_merchant_city="Sao Paulo",  # 9 chars
            created_at=now,
            updated_at=now,
        )
        result = serialize_organization(org)

        assert result["pix_key"] == "123...90"
        assert result["pix_merchant_name"] == "Acm...ia"
        assert result["pix_merchant_city"] == "Sao...lo"


class TestSerializeInvite:
    def test_basic_invite_redacts_emails_and_drops_org_name(self):
        now = datetime(2026, 2, 10, 8, 0, 0)
        invite = Invite(
            id=1,
            uuid="inv123",
            organization_id=3,
            organization_name="Org A",
            invited_user_id=5,
            invited_email="bob@example.com",
            invited_by_user_id=1,
            invited_by_email="alice@example.com",
            role="viewer",
            status="pending",
            created_at=now,
            responded_at=None,
        )
        result = serialize_invite(invite)

        assert result["id"] == 1
        assert result["uuid"] == "inv123"
        assert result["organization_id"] == 3
        # organization_name intentionally NOT in audit payload — the row
        # references the org by id, and the name is captured under the
        # dedicated organization audit events via serialize_organization.
        assert "organization_name" not in result
        assert result["invited_user_id"] == 5
        # first 2 chars of local + ...@ + full domain
        assert result["invited_email"] == "bo...@example.com"
        assert result["invited_by_user_id"] == 1
        assert result["invited_by_email"] == "al...@example.com"
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

    def test_invite_short_local_collapses_and_empty_stays_empty(self):
        """Edge-case email values go through the same partial-mask rules
        as ``serialize_user``: 1-char local-parts collapse to ``***@<domain>``
        and empty values round-trip as ``""``.
        """
        invite = Invite(
            organization_id=1,
            invited_user_id=2,
            invited_email="a@b.co",
            invited_by_user_id=3,
            invited_by_email="",
        )
        result = serialize_invite(invite)
        # Empty email → "" (redact returns "" on empty input).
        assert result["invited_by_email"] == ""
        # Short local-part collapses to "***@<domain>" — see
        # rentivo.pii_redaction._mask_email.
        assert result["invited_email"] == "***@b.co"
        # And in no case do we leak the plaintext local-part.
        assert "a@b.co" not in result["invited_email"]

    def test_invite_email_redaction_is_deterministic(self):
        """Same plaintext email → same redacted form; key-less mask."""
        a = serialize_invite(
            Invite(
                organization_id=1,
                invited_user_id=2,
                invited_email="alice@example.com",
                invited_by_user_id=3,
                invited_by_email="carol@example.com",
            )
        )
        b = serialize_invite(
            Invite(
                organization_id=1,
                invited_user_id=2,
                invited_email="alice@example.com",
                invited_by_user_id=3,
                invited_by_email="dan@example.com",
            )
        )
        assert a["invited_email"] == b["invited_email"] == "al...@example.com"
        assert a["invited_by_email"] != b["invited_by_email"]


class TestSerializeJobPayload:
    def test_email_send_partial_mask_redacts_to_email_drops_ctx_values(self):
        result = serialize_job_payload(
            {
                "job_type": "email.send",
                "event": "welcome",
                "to_email": "alice@example.com",
                "ctx": {"email": "alice@example.com", "pix_setup_url": "http://x/pix"},
            }
        )

        assert result["event"] == "welcome"
        assert result["to_email"] == "al...@example.com"  # first 2 + ...@ + domain
        assert result["ctx_keys_count"] == 2
        assert "ctx" not in result
        assert "pix_setup_url" not in result
        assert "to_email_hash" not in result  # old hash form is gone

    def test_email_send_redaction_is_deterministic(self):
        a = serialize_job_payload({"job_type": "email.send", "event": "welcome", "to_email": "alice@example.com"})
        b = serialize_job_payload(
            {"job_type": "email.send", "event": "password_reset", "to_email": "alice@example.com"}
        )
        c = serialize_job_payload({"job_type": "email.send", "event": "welcome", "to_email": "bob@example.com"})

        assert a["to_email"] == b["to_email"] == "al...@example.com"
        assert a["to_email"] != c["to_email"]

    def test_email_send_empty_to_email_yields_empty_string(self):
        result = serialize_job_payload({"job_type": "email.send", "event": "welcome"})
        assert result["to_email"] == ""

        result_empty = serialize_job_payload({"job_type": "email.send", "event": "welcome", "to_email": ""})
        assert result_empty["to_email"] == ""

    def test_email_send_with_ctx_none_does_not_raise(self):
        result = serialize_job_payload({"job_type": "email.send", "ctx": None})

        assert result["ctx_keys_count"] == 0

    def test_strips_disallowed_keys(self):
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
        result = serialize_job_payload({"job_type": "pdf.render", "bill_id": 7, "force": True})

        assert result == {"job_type": "pdf.render", "keys": ["bill_id", "force", "job_type"]}

    def test_unknown_job_type_strips_disallowed_keys_from_index(self):
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

    def test_unknown_job_type_strips_pix_merchant_wildcard(self):
        result = serialize_job_payload(
            {
                "job_type": "pdf.render",
                "bill_id": 7,
                "pix_merchant_id": "abc-123",
                "pix_merchant_email": "alice@x",
                "pix_merchant_anything_else": "x",
            }
        )

        assert result == {"job_type": "pdf.render", "keys": ["bill_id", "job_type"]}

    def test_missing_job_type_falls_through_to_unknown_branch(self):
        result = serialize_job_payload({"foo": "bar"})

        assert result == {"job_type": "", "keys": ["foo"]}

    def test_s3_delete_keeps_key(self):
        result = serialize_job_payload({"job_type": "s3.delete", "key": "01HX/01HZ.pdf"})

        assert result == {"key": "01HX/01HZ.pdf"}

    def test_s3_delete_missing_key_yields_empty_string(self):
        result = serialize_job_payload({"job_type": "s3.delete"})

        assert result == {"key": ""}

    def test_s3_delete_with_extra_payload_keys_ignores_them(self):
        # Forward compatibility: if a caller adds metadata to the payload,
        # the audit serializer keeps only `key` to avoid leaking unknown values.
        result = serialize_job_payload({"job_type": "s3.delete", "key": "k", "bucket": "secret", "actor": "x"})

        assert result == {"key": "k"}


class TestSerializeTheme:
    def test_serialize_theme(self):
        theme = Theme(
            id=1,
            uuid="t-uuid",
            owner_type="billing",
            owner_id=3,
            name="Custom",
            header_font="Roboto",
            text_font="Lora",
            primary="#111111",
            primary_light="#222222",
            secondary="#333333",
            secondary_dark="#444444",
            text_color="#555555",
            text_contrast="#666666",
        )
        assert serialize_theme(theme) == {
            "uuid": "t-uuid",
            "owner_type": "billing",
            "owner_id": 3,
            "name": "Custom",
            "header_font": "Roboto",
            "text_font": "Lora",
            "primary": "#111111",
            "primary_light": "#222222",
            "secondary": "#333333",
            "secondary_dark": "#444444",
            "text_color": "#555555",
            "text_contrast": "#666666",
        }
