from datetime import datetime
from unittest.mock import patch

import pytest

from rentivo.constants import SP_TZ
from rentivo.models.bill import BillLineItem
from rentivo.models.billing import ItemType


class TestBillRepoCRUD:
    def _create_billing(self, billing_repo, sample_billing):
        return billing_repo.create(sample_billing())

    def test_create_and_get(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        bill = sample_bill(billing_id=billing.id)
        created = bill_repo.create(bill)

        assert created.id is not None
        assert created.uuid != ""
        assert created.billing_id == billing.id
        assert len(created.line_items) == 2
        assert created.total_amount == 295000

    def test_get_by_id_not_found(self, bill_repo):
        assert bill_repo.get_by_id(9999) is None

    def test_get_by_uuid(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        fetched = bill_repo.get_by_uuid(created.uuid)

        assert fetched is not None
        assert fetched.uuid == created.uuid

    def test_get_by_uuid_not_found(self, bill_repo):
        assert bill_repo.get_by_uuid("nonexistent") is None

    def test_list_by_billing(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        bill_repo.create(sample_bill(billing_id=billing.id, reference_month="2025-01"))
        bill_repo.create(sample_bill(billing_id=billing.id, reference_month="2025-02"))

        bills = bill_repo.list_by_billing(billing.id)
        assert len(bills) == 2

    def test_list_by_billing_empty(self, bill_repo, billing_repo, sample_billing):
        billing = self._create_billing(billing_repo, sample_billing)
        assert bill_repo.list_by_billing(billing.id) == []

    def test_list_by_billing_with_multiple_bills_loads_line_items(
        self, bill_repo, billing_repo, sample_billing, sample_bill
    ):
        """Bulk-load (IN-query) path: list_by_billing() must hydrate line items for every bill."""
        billing = self._create_billing(billing_repo, sample_billing)
        bill_repo.create(sample_bill(billing_id=billing.id, reference_month="2026-01"))
        bill_repo.create(sample_bill(billing_id=billing.id, reference_month="2026-02"))
        bill_repo.create(sample_bill(billing_id=billing.id, reference_month="2026-03"))

        bills = bill_repo.list_by_billing(billing.id)

        assert len(bills) == 3
        for bill in bills:
            assert len(bill.line_items) == 2
            assert all(isinstance(item, BillLineItem) for item in bill.line_items)

    def test_update(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        created.notes = "Updated notes"
        created.line_items = [
            BillLineItem(description="New item", amount=50000, item_type=ItemType.FIXED, sort_order=0),
        ]
        created.total_amount = 50000
        updated = bill_repo.update(created)

        assert updated.notes == "Updated notes"
        assert len(updated.line_items) == 1
        assert updated.total_amount == 50000

    def test_update_pdf_path(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        bill_repo.update_pdf_path(created.id, "/new/path.pdf")

        fetched = bill_repo.get_by_id(created.id)
        assert fetched.pdf_path == "/new/path.pdf"

    def test_update_status(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        now = datetime.now(SP_TZ)
        bill_repo.update_status(created.id, "paid", now)

        fetched = bill_repo.get_by_id(created.id)
        assert fetched.status == "paid"
        assert fetched.status_updated_at is not None

    def test_update_status_back_to_draft(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        now = datetime.now(SP_TZ)
        bill_repo.update_status(created.id, "paid", now)
        bill_repo.update_status(created.id, "draft", now)

        fetched = bill_repo.get_by_id(created.id)
        assert fetched.status == "draft"

    def test_soft_delete(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        bill_repo.delete(created.id)

        assert bill_repo.get_by_id(created.id) is None
        assert bill_repo.list_by_billing(billing.id) == []

    def test_soft_delete_hides_from_uuid(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        bill_repo.delete(created.id)
        assert bill_repo.get_by_uuid(created.uuid) is None


class TestBillRepoEdgeCases:
    def _create_billing(self, billing_repo, sample_billing):
        return billing_repo.create(sample_billing())

    def test_create_runtime_error(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        bill = sample_bill(billing_id=billing.id)
        with patch.object(bill_repo, "get_by_id", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve bill after create"):
                bill_repo.create(bill)

    def test_update_runtime_error(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        created.notes = "Updated"
        with patch.object(bill_repo, "get_by_id", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve bill after update"):
                bill_repo.update(created)


class TestBillRepoPdfRenderStatus:
    def _create_billing(self, billing_repo, sample_billing):
        return billing_repo.create(sample_billing())

    def test_update_pdf_render_status_sets_pending(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        bill_repo.update_pdf_render_status(created.id, "pending")

        fetched = bill_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.pdf_render_status == "pending"

    def test_update_pdf_render_status_can_set_to_null(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        bill_repo.update_pdf_render_status(created.id, "pending")
        bill_repo.update_pdf_render_status(created.id, None)

        fetched = bill_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.pdf_render_status is None

    def test_get_by_id_returns_pdf_render_status(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        bill_repo.update_pdf_render_status(created.id, "succeeded")

        fetched = bill_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.pdf_render_status == "succeeded"

    def test_default_pdf_render_status_is_none(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        assert created.pdf_render_status is None


class TestBillRepoEncryptionWiring:
    def test_constructor_accepts_encryption_backend(self, db_connection, fake_encryption):
        from rentivo.repositories.sqlalchemy import SQLAlchemyBillRepository

        repo = SQLAlchemyBillRepository(db_connection, fake_encryption)
        assert repo.encryption is fake_encryption

    def test_factory_passes_encryption_backend(self, monkeypatch):
        from unittest.mock import MagicMock

        from rentivo.repositories.factory import get_bill_repository

        called = {}

        class FakeRepo:
            def __init__(self, conn, encryption):
                called["conn"] = conn
                called["encryption"] = encryption

        monkeypatch.setattr("rentivo.db.get_connection", lambda: MagicMock())
        monkeypatch.setattr(
            "rentivo.repositories.sqlalchemy.SQLAlchemyBillRepository",
            FakeRepo,
        )
        repo = get_bill_repository()
        assert repo is not None
        assert called["encryption"] is not None


class TestBillRepoEncryption:
    """Verifies that the repository routes notes and line-item descriptions through encryption."""

    def test_create_encrypts_notes_and_line_item_descriptions(
        self, db_connection, fake_encryption, sample_billing, sample_bill
    ):
        from sqlalchemy import text

        from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository, SQLAlchemyBillRepository

        billing_repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
        billing = billing_repo.create(sample_billing())

        repo = SQLAlchemyBillRepository(db_connection, fake_encryption)
        created = repo.create(sample_bill(billing_id=billing.id, notes="Pagar até o dia 5"))

        row = (
            db_connection.execute(
                text("SELECT notes FROM bills WHERE id = :id"),
                {"id": created.id},
            )
            .mappings()
            .fetchone()
        )
        assert row["notes"] == "fake:Pagar até o dia 5"

        item_rows = (
            db_connection.execute(
                text("SELECT description FROM bill_line_items WHERE bill_id = :id ORDER BY sort_order"),
                {"id": created.id},
            )
            .mappings()
            .fetchall()
        )
        assert [r["description"] for r in item_rows] == ["fake:Aluguel", "fake:Água"]

    def test_get_decrypts_notes_and_line_item_descriptions(
        self, db_connection, fake_encryption, sample_billing, sample_bill
    ):
        from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository, SQLAlchemyBillRepository

        billing_repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
        billing = billing_repo.create(sample_billing())

        repo = SQLAlchemyBillRepository(db_connection, fake_encryption)
        created = repo.create(sample_bill(billing_id=billing.id, notes="Pagar até o dia 5"))

        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.notes == "Pagar até o dia 5"
        assert [item.description for item in fetched.line_items] == ["Aluguel", "Água"]

    def test_update_re_encrypts_notes_and_line_items(self, db_connection, fake_encryption, sample_billing, sample_bill):
        from sqlalchemy import text

        from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository, SQLAlchemyBillRepository

        billing_repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
        billing = billing_repo.create(sample_billing())

        repo = SQLAlchemyBillRepository(db_connection, fake_encryption)
        created = repo.create(sample_bill(billing_id=billing.id, notes="old"))
        created.notes = "new"
        created.line_items[0].description = "Aluguel atualizado"
        repo.update(created)

        row = (
            db_connection.execute(
                text("SELECT notes FROM bills WHERE id = :id"),
                {"id": created.id},
            )
            .mappings()
            .fetchone()
        )
        assert row["notes"] == "fake:new"

        item_rows = (
            db_connection.execute(
                text("SELECT description FROM bill_line_items WHERE bill_id = :id ORDER BY sort_order"),
                {"id": created.id},
            )
            .mappings()
            .fetchall()
        )
        assert item_rows[0]["description"] == "fake:Aluguel atualizado"

    def test_list_by_billing_decrypts(self, db_connection, fake_encryption, sample_billing, sample_bill):
        from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository, SQLAlchemyBillRepository

        billing_repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
        billing = billing_repo.create(sample_billing())

        repo = SQLAlchemyBillRepository(db_connection, fake_encryption)
        repo.create(sample_bill(billing_id=billing.id, notes="Note A", reference_month="2025-01"))
        repo.create(sample_bill(billing_id=billing.id, notes="Note B", reference_month="2025-02"))

        bills = repo.list_by_billing(billing.id)
        notes = sorted(b.notes for b in bills)
        assert notes == ["Note A", "Note B"]
        for b in bills:
            assert [li.description for li in b.line_items] == ["Aluguel", "Água"]

    def test_get_handles_legacy_plaintext_rows(self, db_connection, fake_encryption, sample_billing):
        from sqlalchemy import text

        from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository, SQLAlchemyBillRepository

        billing_repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
        billing = billing_repo.create(sample_billing())

        # Insert a plaintext bill directly to simulate a pre-backfill row.
        db_connection.execute(
            text(
                "INSERT INTO bills (billing_id, reference_month, total_amount, "
                "pdf_path, notes, uuid, due_date, status, status_updated_at, created_at) "
                "VALUES (:bid, '2025-03', 100, NULL, 'legacy notes', "
                "'01HXLEGACYBILL0000000000000', '10/04/2025', 'draft', "
                "'2026-04-01 00:00:00', '2026-04-01 00:00:00')"
            ),
            {"bid": billing.id},
        )
        bill_id = db_connection.execute(
            text("SELECT id FROM bills WHERE uuid = '01HXLEGACYBILL0000000000000'")
        ).scalar_one()
        db_connection.execute(
            text(
                "INSERT INTO bill_line_items (bill_id, description, amount, item_type, sort_order) "
                "VALUES (:bid, 'legacy item', 100, 'fixed', 0)"
            ),
            {"bid": bill_id},
        )
        db_connection.commit()

        repo = SQLAlchemyBillRepository(db_connection, fake_encryption)
        fetched = repo.get_by_id(bill_id)
        assert fetched is not None
        assert fetched.notes == "legacy notes"
        assert fetched.line_items[0].description == "legacy item"
