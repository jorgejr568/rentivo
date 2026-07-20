from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from rentivo.constants import SP_TZ
from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import ItemType
from rentivo.repositories.sqlalchemy import SQLAlchemyBillRepository


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

    def test_update_recibo_pdf_path(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        assert bill_repo.get_by_id(created.id).recibo_pdf_path is None

        bill_repo.update_recibo_pdf_path(created.id, "/r/recibo.pdf")
        assert bill_repo.get_by_id(created.id).recibo_pdf_path == "/r/recibo.pdf"

        # Clearing it (bill leaves PAID) round-trips back to None.
        bill_repo.update_recibo_pdf_path(created.id, None)
        assert bill_repo.get_by_id(created.id).recibo_pdf_path is None

    def test_update_status(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        now = datetime.now(SP_TZ)
        assert bill_repo.update_status(created.id, "draft", created.status_updated_at, "paid", now) is True

        fetched = bill_repo.get_by_id(created.id)
        assert fetched.status == "paid"
        assert fetched.status_updated_at is not None

    def test_update_status_back_to_draft(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        now = datetime.now(SP_TZ)
        later = now + timedelta(seconds=1)
        assert bill_repo.update_status(created.id, "draft", created.status_updated_at, "paid", now) is True
        assert bill_repo.update_status(created.id, "paid", now, "draft", later) is True

        fetched = bill_repo.get_by_id(created.id)
        assert fetched.status == "draft"

    def test_update_status_rejects_stale_expected_status(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        now = datetime.now(SP_TZ)

        assert bill_repo.update_status(created.id, "sent", created.status_updated_at, "paid", now) is False
        assert bill_repo.get_by_id(created.id).status == "draft"

    def test_update_status_rejects_aba_with_stale_status_timestamp(
        self,
        bill_repo,
        billing_repo,
        sample_billing,
        sample_bill,
    ):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id, status="draft"))
        original_version = created.status_updated_at
        sent_version = original_version + timedelta(seconds=1)
        returned_version = sent_version + timedelta(seconds=1)

        assert bill_repo.update_status(created.id, "draft", original_version, "sent", sent_version) is True
        assert bill_repo.update_status(created.id, "sent", sent_version, "draft", returned_version) is True
        assert (
            bill_repo.update_status(
                created.id,
                "draft",
                original_version,
                "paid",
                returned_version + timedelta(seconds=1),
            )
            is False
        )

        current = bill_repo.get_by_id(created.id)
        assert current.status == "draft"
        assert current.status_updated_at == returned_version

    def test_leaving_paid_atomically_returns_and_clears_current_recibo_path(
        self,
        bill_repo,
        billing_repo,
        sample_billing,
        sample_bill,
    ):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id, status="paid"))
        bill_repo.update_recibo_pdf_path(created.id, "current/recibo.pdf")
        cancelled_at = created.status_updated_at + timedelta(seconds=1)

        updated, current_path = bill_repo.update_status_and_clear_recibo(
            created.id,
            "paid",
            created.status_updated_at,
            "cancelled",
            cancelled_at,
        )

        assert updated is True
        assert current_path == "current/recibo.pdf"
        persisted = bill_repo.get_by_id(created.id)
        assert persisted.status == "cancelled"
        assert persisted.status_updated_at == cancelled_at
        assert persisted.recibo_pdf_path is None

    def test_leaving_paid_atomic_clear_rejects_stale_version(
        self,
        bill_repo,
        billing_repo,
        sample_billing,
        sample_bill,
    ):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id, status="paid"))

        assert bill_repo.update_status_and_clear_recibo(
            created.id,
            "paid",
            created.status_updated_at + timedelta(seconds=1),
            "cancelled",
            created.status_updated_at + timedelta(seconds=2),
        ) == (False, None)
        assert bill_repo.get_by_id(created.id).status == "paid"

    def test_leaving_paid_atomic_clear_rolls_back_repository_error(self, fake_encryption):
        conn = MagicMock()
        conn.dialect.name = "sqlite"
        conn.execute.side_effect = RuntimeError("database failed")
        repo = SQLAlchemyBillRepository(conn, fake_encryption)

        with pytest.raises(RuntimeError, match="database failed"):
            repo.update_status_and_clear_recibo(1, "paid", None, "sent", datetime.now(SP_TZ))

        conn.rollback.assert_called_once_with()

    def test_leaving_paid_atomic_clear_handles_lost_update_after_read(self, fake_encryption):
        conn = MagicMock()
        conn.dialect.name = "sqlite"
        selected = MagicMock()
        selected.mappings.return_value.fetchone.return_value = {"recibo_pdf_path": "current.pdf"}
        updated = MagicMock(rowcount=0)
        conn.execute.side_effect = [selected, updated]
        repo = SQLAlchemyBillRepository(conn, fake_encryption)

        assert repo.update_status_and_clear_recibo(1, "paid", None, "sent", datetime.now(SP_TZ)) == (
            False,
            None,
        )
        conn.commit.assert_called_once_with()

    def test_paid_version_guards_recibo_path_replacement(
        self,
        bill_repo,
        billing_repo,
        sample_billing,
        sample_bill,
    ):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id, status="paid"))
        bill_repo.update_recibo_pdf_path(created.id, "old/recibo.pdf")

        assert bill_repo.replace_recibo_pdf_path_if_paid_version(
            created.id,
            created.status_updated_at,
            "old/recibo.pdf",
            "new/recibo.pdf",
        ) == (True, "old/recibo.pdf")
        assert bill_repo.replace_recibo_pdf_path_if_paid_version(
            created.id,
            created.status_updated_at,
            "old/recibo.pdf",
            "stale/recibo.pdf",
        ) == (False, "new/recibo.pdf")
        assert bill_repo.get_by_id(created.id).recibo_pdf_path == "new/recibo.pdf"
        assert bill_repo.replace_recibo_pdf_path_if_paid_version(
            created.id,
            created.status_updated_at + timedelta(seconds=1),
            "new/recibo.pdf",
            "too-late/recibo.pdf",
        ) == (False, None)

    def test_recibo_path_replacement_rolls_back_repository_error(self, fake_encryption):
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError("database failed")
        repo = SQLAlchemyBillRepository(conn, fake_encryption)

        with pytest.raises(RuntimeError, match="database failed"):
            repo.replace_recibo_pdf_path_if_paid_version(1, None, None, "candidate.pdf")

        conn.rollback.assert_called_once_with()

    def test_soft_delete(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        assert bill_repo.delete(created.id) is True

        assert bill_repo.get_by_id(created.id) is None
        assert bill_repo.list_by_billing(billing.id) == []
        assert bill_repo.delete(created.id) is False

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

    def test_create_rolls_back_insert_and_line_items_when_hydration_fails(
        self,
        db_connection,
        fake_encryption,
        billing_repo,
        sample_billing,
        sample_bill,
    ):
        billing = self._create_billing(billing_repo, sample_billing)
        failing_encryption = MagicMock(wraps=fake_encryption)
        failing_encryption.decrypt_many.side_effect = RuntimeError("decrypt failed")
        repo = SQLAlchemyBillRepository(db_connection, failing_encryption)

        with pytest.raises(RuntimeError, match="decrypt failed"):
            repo.create(sample_bill(billing_id=billing.id))

        assert db_connection.execute(text("SELECT COUNT(*) FROM bills")).scalar_one() == 0
        assert db_connection.execute(text("SELECT COUNT(*) FROM bill_line_items")).scalar_one() == 0

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

    def test_get_pdf_render_state_returns_empty_state_for_missing_bill(self, bill_repo):
        assert bill_repo.get_pdf_render_state(9999) == (None, None, None)

    def test_render_operation_token_prevents_stale_completion(
        self,
        bill_repo,
        billing_repo,
        sample_billing,
        sample_bill,
    ):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))

        bill_repo.begin_pdf_render(created.id, "01JRENDEROPERATION000000001")
        bill_repo.begin_pdf_render(created.id, "01JRENDEROPERATION000000002")

        assert bill_repo.finish_pdf_render(created.id, "01JRENDEROPERATION000000001", "failed") is False
        assert bill_repo.get_by_id(created.id).pdf_render_status == "pending"
        assert bill_repo.finish_pdf_render(created.id, "01JRENDEROPERATION000000002", "succeeded") is True
        assert bill_repo.get_by_id(created.id).pdf_render_status == "succeeded"

    def test_restore_after_failed_render_is_atomic_guarded_and_idempotent(
        self,
        bill_repo,
        billing_repo,
        sample_billing,
        sample_bill,
    ):
        billing = self._create_billing(billing_repo, sample_billing)
        previous = bill_repo.create(sample_bill(billing_id=billing.id, pdf_path="old.pdf"))
        bill_repo.update_pdf_render_status(previous.id, "succeeded")
        previous = bill_repo.get_by_id(previous.id)
        changed = previous.model_copy(deep=True)
        changed.notes = "changed"
        changed.total_amount = 321
        changed.line_items = [BillLineItem(description="changed", amount=321, item_type=ItemType.EXTRA, sort_order=0)]
        candidate = bill_repo.update(changed)
        operation_id = "01JRENDEROPERATION000000001"
        bill_repo.begin_pdf_render(previous.id, operation_id)

        assert bill_repo.restore_after_failed_render(previous, candidate, operation_id) is True
        assert bill_repo.restore_after_failed_render(previous, candidate, operation_id) is True

        restored = bill_repo.get_by_id(previous.id)
        assert restored.notes == previous.notes
        assert restored.total_amount == previous.total_amount
        assert [item.description for item in restored.line_items] == [item.description for item in previous.line_items]
        assert restored.pdf_path == "old.pdf"
        assert restored.pdf_render_status == "succeeded"
        assert bill_repo.get_pdf_render_state(previous.id) == (None, "succeeded", "old.pdf")

        bill_repo.begin_pdf_render(previous.id, "01JRENDEROPERATION000000002")
        assert bill_repo.restore_after_failed_render(previous, candidate, operation_id) is False
        assert bill_repo.get_pdf_render_state(previous.id)[0] == "01JRENDEROPERATION000000002"

    @pytest.mark.parametrize("changed_field", ["notes", "line_items"])
    def test_restore_after_failed_render_rejects_newer_candidate_state(
        self,
        bill_repo,
        billing_repo,
        sample_billing,
        sample_bill,
        changed_field,
    ):
        billing = self._create_billing(billing_repo, sample_billing)
        previous = bill_repo.create(sample_bill(billing_id=billing.id, pdf_path="old.pdf"))
        bill_repo.update_pdf_render_status(previous.id, "succeeded")
        previous = bill_repo.get_by_id(previous.id)
        candidate = previous.model_copy(deep=True)
        candidate.notes = "request-a"
        candidate.line_items = [
            BillLineItem(description="request-a", amount=321, item_type=ItemType.EXTRA, sort_order=0),
        ]
        candidate.total_amount = 321
        candidate = bill_repo.update(candidate)
        operation_id = "01JRENDEROPERATION000000001"
        bill_repo.begin_pdf_render(previous.id, operation_id)

        newer = candidate.model_copy(deep=True)
        if changed_field == "notes":
            newer.notes = "request-b"
        else:
            newer.line_items = [
                BillLineItem(description="request-b", amount=321, item_type=ItemType.EXTRA, sort_order=0),
            ]
        bill_repo.update(newer)

        assert bill_repo.restore_after_failed_render(previous, candidate, operation_id) is False
        persisted = bill_repo.get_by_id(previous.id)
        assert persisted.notes == newer.notes
        assert [(item.description, item.amount) for item in persisted.line_items] == [
            (item.description, item.amount) for item in newer.line_items
        ]
        assert bill_repo.get_pdf_render_state(previous.id)[0] == operation_id

    def test_restore_after_failed_render_rejects_newer_identical_candidate_revision(
        self,
        bill_repo,
        billing_repo,
        sample_billing,
        sample_bill,
    ):
        billing = self._create_billing(billing_repo, sample_billing)
        previous = bill_repo.create(sample_bill(billing_id=billing.id, pdf_path="old.pdf"))
        bill_repo.update_pdf_render_status(previous.id, "succeeded")
        previous = bill_repo.get_by_id(previous.id)
        changed = previous.model_copy(deep=True)
        changed.notes = "same candidate"
        candidate_a = bill_repo.update(changed)
        operation_id = "01JRENDEROPERATION000000001"
        bill_repo.begin_pdf_render(previous.id, operation_id)

        candidate_b = bill_repo.update(candidate_a.model_copy(deep=True))

        assert candidate_b.mutation_revision > candidate_a.mutation_revision
        assert bill_repo.restore_after_failed_render(previous, candidate_a, operation_id) is False
        persisted = bill_repo.get_by_id(previous.id)
        assert persisted.notes == "same candidate"
        assert persisted.mutation_revision == candidate_b.mutation_revision
        assert bill_repo.get_pdf_render_state(previous.id)[0] == operation_id

    def test_restore_after_failed_render_rejects_missing_id(self, bill_repo):
        with pytest.raises(ValueError, match="without an id"):
            bill_repo.restore_after_failed_render(
                Bill(billing_id=1, reference_month="2026-07"),
                Bill(billing_id=1, reference_month="2026-07"),
                "operation",
            )

    def test_restore_after_failed_render_returns_false_for_missing_bill(self, bill_repo):
        assert (
            bill_repo.restore_after_failed_render(
                Bill(id=9999, billing_id=1, reference_month="2026-07"),
                Bill(id=9999, billing_id=1, reference_month="2026-07"),
                "operation",
            )
            is False
        )

    @pytest.mark.parametrize(
        ("dialect_name", "expected_sql"),
        [
            (
                "sqlite",
                [
                    "UPDATE bills SET pdf_render_operation_id = pdf_render_operation_id WHERE id = :id "
                    "AND pdf_render_operation_id = :operation_id AND deleted_at IS NULL",
                    "SELECT * FROM bills WHERE id = :id AND deleted_at IS NULL",
                ],
            ),
            ("mysql", ["SELECT * FROM bills WHERE id = :id AND deleted_at IS NULL FOR UPDATE"]),
        ],
    )
    def test_restore_after_failed_render_uses_dialect_appropriate_lock(
        self,
        fake_encryption,
        dialect_name,
        expected_sql,
    ):
        conn = MagicMock()
        conn.dialect.name = dialect_name
        selected = MagicMock()
        selected.mappings.return_value.fetchone.return_value = None
        conn.execute.return_value = selected
        repo = SQLAlchemyBillRepository(conn, fake_encryption)

        assert (
            repo.restore_after_failed_render(
                Bill(id=1, billing_id=1, reference_month="2026-07"),
                Bill(id=1, billing_id=1, reference_month="2026-07"),
                "operation",
            )
            is False
        )

        statements = [str(call.args[0]) for call in conn.execute.call_args_list]
        assert statements == expected_sql

    def test_restore_candidate_hydration_locks_line_items_on_mysql(self, fake_encryption):
        conn = MagicMock()
        conn.dialect.name = "mysql"
        conn.execute.return_value.mappings.return_value.fetchall.return_value = []
        repo = SQLAlchemyBillRepository(conn, fake_encryption)
        hydrated = Bill(id=1, billing_id=1, reference_month="2026-07")

        with patch.object(repo, "_build_bills", return_value=[hydrated]):
            assert repo._row_to_bill({"id": 1}, lock=True) is hydrated

        statement = conn.execute.call_args.args[0]
        assert str(statement) == (
            "SELECT * FROM bill_line_items WHERE bill_id = :bill_id ORDER BY sort_order FOR UPDATE"
        )

    def test_restore_after_failed_render_rolls_back_lost_update(self, fake_encryption):
        conn = MagicMock()
        conn.dialect.name = "mysql"
        selected = MagicMock()
        selected.mappings.return_value.fetchone.return_value = {
            "pdf_render_operation_id": "operation",
        }
        conn.execute.side_effect = [selected, MagicMock(rowcount=0)]
        repo = SQLAlchemyBillRepository(conn, fake_encryption)
        candidate = Bill(id=1, billing_id=1, reference_month="2026-07")

        with patch.object(repo, "_row_to_bill", return_value=candidate):
            assert (
                repo.restore_after_failed_render(
                    Bill(id=1, billing_id=1, reference_month="2026-07"),
                    candidate,
                    "operation",
                )
                is False
            )
        conn.rollback.assert_called_once_with()

    def test_restore_after_failed_render_rejects_content_mismatch_at_same_revision(self, fake_encryption):
        conn = MagicMock()
        conn.dialect.name = "mysql"
        selected = MagicMock()
        selected.mappings.return_value.fetchone.return_value = {
            "pdf_render_operation_id": "operation",
        }
        conn.execute.return_value = selected
        repo = SQLAlchemyBillRepository(conn, fake_encryption)
        candidate = Bill(
            id=1,
            billing_id=1,
            reference_month="2026-07",
            notes="candidate",
            mutation_revision=3,
        )
        current = candidate.model_copy(update={"notes": "unexpected"})

        with patch.object(repo, "_row_to_bill", return_value=current):
            assert (
                repo.restore_after_failed_render(
                    Bill(id=1, billing_id=1, reference_month="2026-07"),
                    candidate,
                    "operation",
                )
                is False
            )

        conn.commit.assert_called_once_with()

    def test_restore_after_failed_render_rolls_back_repository_error(self, fake_encryption):
        conn = MagicMock()
        conn.dialect.name = "sqlite"
        conn.execute.side_effect = RuntimeError("database failed")
        repo = SQLAlchemyBillRepository(conn, fake_encryption)

        with pytest.raises(RuntimeError, match="database failed"):
            repo.restore_after_failed_render(
                Bill(id=1, billing_id=1, reference_month="2026-07"),
                Bill(id=1, billing_id=1, reference_month="2026-07"),
                "operation",
            )

        conn.rollback.assert_called_once_with()

    def test_publish_pdf_render_atomically_replaces_path_for_owned_operation(
        self,
        bill_repo,
        billing_repo,
        sample_billing,
        sample_bill,
    ):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id, pdf_path="old.pdf"))
        bill_repo.begin_pdf_render(created.id, "01JRENDEROPERATION000000001")
        bill_repo.begin_pdf_render(created.id, "01JRENDEROPERATION000000002")

        assert bill_repo.publish_pdf_render(
            created.id,
            "01JRENDEROPERATION000000001",
            "candidate-a.pdf",
        ) == (False, "old.pdf")
        assert bill_repo.publish_pdf_render(
            created.id,
            "01JRENDEROPERATION000000002",
            "candidate-b.pdf",
        ) == (True, "old.pdf")

        persisted = bill_repo.get_by_id(created.id)
        assert persisted.pdf_path == "candidate-b.pdf"
        assert persisted.pdf_render_status == "succeeded"
        assert (
            bill_repo.finish_pdf_render(
                created.id,
                "01JRENDEROPERATION000000002",
                "failed",
            )
            is False
        )

    def test_publish_pdf_render_rolls_back_repository_error(self, fake_encryption):
        conn = MagicMock()
        conn.dialect.name = "sqlite"
        conn.execute.side_effect = RuntimeError("database failed")
        repo = SQLAlchemyBillRepository(conn, fake_encryption)

        with pytest.raises(RuntimeError, match="database failed"):
            repo.publish_pdf_render(1, "01JRENDEROPERATION000000001", "candidate.pdf")

        conn.rollback.assert_called_once_with()

    def test_publish_pdf_render_handles_lost_update_after_locked_read(self, fake_encryption):
        conn = MagicMock()
        conn.dialect.name = "sqlite"
        selected = MagicMock()
        selected.mappings.return_value.fetchone.return_value = {
            "pdf_path": "old.pdf",
            "pdf_render_operation_id": "01JRENDEROPERATION000000001",
        }
        updated = MagicMock(rowcount=0)
        current = MagicMock()
        current.mappings.return_value.fetchone.return_value = {"pdf_path": "winner.pdf"}
        conn.execute.side_effect = [selected, updated, current]
        repo = SQLAlchemyBillRepository(conn, fake_encryption)

        assert repo.publish_pdf_render(
            1,
            "01JRENDEROPERATION000000001",
            "candidate.pdf",
        ) == (False, "winner.pdf")
        conn.commit.assert_called_once_with()

    def test_legacy_pending_render_claim_and_failure_are_conditional(
        self,
        bill_repo,
        billing_repo,
        sample_billing,
        sample_bill,
    ):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        bill_repo.update_pdf_render_status(created.id, "pending")

        assert (
            bill_repo.claim_pending_pdf_render(
                created.id,
                "01JLEGACYRENDER000000000001",
            )
            is True
        )
        assert (
            bill_repo.claim_pending_pdf_render(
                created.id,
                "01JLEGACYRENDER000000000001",
            )
            is True
        )
        assert (
            bill_repo.claim_pending_pdf_render(
                created.id,
                "01JLEGACYRENDER000000000002",
            )
            is False
        )
        assert bill_repo.fail_pending_pdf_render_without_operation(created.id) is False
        assert (
            bill_repo.finish_pdf_render(
                created.id,
                "01JLEGACYRENDER000000000001",
                "pending",
            )
            is True
        )
        assert bill_repo.fail_pending_pdf_render_without_operation(created.id) is True
        assert bill_repo.get_by_id(created.id).pdf_render_status == "failed"


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
