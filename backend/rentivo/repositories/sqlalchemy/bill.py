from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from sqlalchemy import Connection, bindparam, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.encryption.base import EncryptionBackend
from rentivo.models.bill import Bill, BillLineItem, BillSummary
from rentivo.models.billing import ItemType
from rentivo.observability import traced
from rentivo.repositories.base import BillRepository
from rentivo.repositories.sqlalchemy._common import _group_rows_by, _now


class SQLAlchemyBillRepository(BillRepository):
    def __init__(self, conn: Connection, encryption: EncryptionBackend) -> None:
        self.conn = conn
        self.encryption = encryption

    @traced("bill_repo.create")
    def create(self, bill: Bill) -> Bill:
        bill_uuid = str(ULID())
        now = _now()
        try:
            result = self.conn.execute(
                text(
                    "INSERT INTO bills (billing_id, reference_month, total_amount, "
                    "pdf_path, notes, uuid, due_date, status, status_updated_at, created_at) "
                    "VALUES (:billing_id, :reference_month, :total_amount, "
                    ":pdf_path, :notes, :uuid, :due_date, :status, :status_updated_at, :created_at)"
                ),
                {
                    "billing_id": bill.billing_id,
                    "reference_month": bill.reference_month,
                    "total_amount": bill.total_amount,
                    "pdf_path": bill.pdf_path,
                    "notes": self.encryption.encrypt(bill.notes),
                    "uuid": bill_uuid,
                    "due_date": bill.due_date,
                    "status": bill.status,
                    "status_updated_at": now,
                    "created_at": now,
                },
            )
            bill_id = result.lastrowid
            for i, item in enumerate(bill.line_items):
                self.conn.execute(
                    text(
                        "INSERT INTO bill_line_items (bill_id, description, amount, item_type, sort_order) "
                        "VALUES (:bill_id, :description, :amount, :item_type, :sort_order)"
                    ),
                    {
                        "bill_id": bill_id,
                        "description": self.encryption.encrypt(item.description),
                        "amount": item.amount,
                        "item_type": item.item_type.value,
                        "sort_order": i,
                    },
                )
            created = self.get_by_id(bill_id)
            if created is None:
                raise RuntimeError(f"Failed to retrieve bill after create (id={bill_id})")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return created

    def _build_bill(
        self,
        row: RowMapping,
        item_rows: list[RowMapping],
        plaintexts: Iterator[str],
    ) -> Bill:
        # Consumes plaintexts in the order produced by ``_gather_bill_ciphertexts``:
        # notes, then one per line item.
        notes = next(plaintexts)
        line_items = [
            BillLineItem(
                id=item_row["id"],
                bill_id=item_row["bill_id"],
                description=next(plaintexts),
                amount=item_row["amount"],
                item_type=ItemType(item_row["item_type"]),
                sort_order=item_row["sort_order"],
            )
            for item_row in item_rows
        ]
        return Bill(
            id=row["id"],
            uuid=row["uuid"],
            billing_id=row["billing_id"],
            reference_month=row["reference_month"],
            total_amount=row["total_amount"],
            line_items=line_items,
            pdf_path=row["pdf_path"],
            recibo_pdf_path=row.get("recibo_pdf_path"),
            notes=notes,
            due_date=row["due_date"],
            status=row.get("status", "draft"),
            status_updated_at=row.get("status_updated_at"),
            pdf_render_status=row.get("pdf_render_status"),
            mutation_revision=row.get("mutation_revision", 0),
            created_at=row["created_at"],
            deleted_at=row["deleted_at"],
        )

    @staticmethod
    def _gather_bill_ciphertexts(
        rows: list[RowMapping],
        items_by_bill: dict[int, list[RowMapping]],
    ) -> list[str]:
        ciphertexts: list[str] = []
        for row in rows:
            ciphertexts.append(row["notes"] or "")
            for item_row in items_by_bill.get(row["id"], []):
                ciphertexts.append(item_row["description"] or "")
        return ciphertexts

    def _build_bills(self, rows: list[RowMapping], items_by_bill: dict[int, list[RowMapping]]) -> list[Bill]:
        """Decrypt every encrypted cell across ``rows`` (and their line items) in
        one batched call, then assemble the models."""
        ciphertexts = self._gather_bill_ciphertexts(rows, items_by_bill)
        plaintexts = iter(self.encryption.decrypt_many(ciphertexts))
        return [self._build_bill(row, items_by_bill.get(row["id"], []), plaintexts) for row in rows]

    def _row_to_bill(self, row: RowMapping, *, lock: bool = False) -> Bill:
        item_query = "SELECT * FROM bill_line_items WHERE bill_id = :bill_id ORDER BY sort_order"
        if lock and self.conn.dialect.name != "sqlite":
            item_query += " FOR UPDATE"
        items = list(
            self.conn.execute(
                text(item_query),
                {"bill_id": row["id"]},
            )
            .mappings()
            .fetchall()
        )
        return self._build_bills([row], {row["id"]: items})[0]

    @traced("bill_repo.get_by_id")
    def get_by_id(self, bill_id: int) -> Bill | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM bills WHERE id = :id AND deleted_at IS NULL"),
                {"id": bill_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_bill(row)

    @traced("bill_repo.get_by_uuid")
    def get_by_uuid(self, uuid: str) -> Bill | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM bills WHERE uuid = :uuid AND deleted_at IS NULL"),
                {"uuid": uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_bill(row)

    @traced("bill_repo.list_by_billing")
    def list_by_billing(self, billing_id: int) -> list[Bill]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT * FROM bills WHERE billing_id = :billing_id "
                    "AND deleted_at IS NULL ORDER BY reference_month DESC"
                ),
                {"billing_id": billing_id},
            )
            .mappings()
            .fetchall()
        )
        if not rows:
            return []
        bill_ids = [row["id"] for row in rows]
        stmt = text("SELECT * FROM bill_line_items WHERE bill_id IN :bill_ids ORDER BY sort_order").bindparams(
            bindparam("bill_ids", expanding=True)
        )
        all_items = self.conn.execute(stmt, {"bill_ids": bill_ids}).mappings().fetchall()
        items_by_bill = _group_rows_by(all_items, "bill_id")
        return self._build_bills(rows, items_by_bill)

    @traced("bill_repo.list_summaries")
    def list_summaries(self, billing_ids: list[int]) -> list[BillSummary]:
        if not billing_ids:
            return []
        stmt = text(
            "SELECT billing_id, total_amount, status, reference_month, due_date "
            "FROM bills WHERE deleted_at IS NULL AND billing_id IN :billing_ids "
            "ORDER BY billing_id ASC, reference_month DESC, id DESC"
        ).bindparams(bindparam("billing_ids", expanding=True))
        rows = self.conn.execute(stmt, {"billing_ids": billing_ids}).mappings().fetchall()
        return [
            BillSummary(
                billing_id=row["billing_id"],
                total_amount=row["total_amount"],
                status=row.get("status", "draft"),
                reference_month=row["reference_month"],
                due_date=row["due_date"],
            )
            for row in rows
        ]

    @traced("bill_repo.update")
    def update(self, bill: Bill) -> Bill:
        self.conn.execute(
            text(
                "UPDATE bills SET reference_month = :reference_month, "
                "total_amount = :total_amount, notes = :notes, due_date = :due_date, "
                "mutation_revision = mutation_revision + 1 WHERE id = :id"
            ),
            {
                "reference_month": bill.reference_month,
                "total_amount": bill.total_amount,
                "notes": self.encryption.encrypt(bill.notes),
                "due_date": bill.due_date,
                "id": bill.id,
            },
        )
        self.conn.execute(
            text("DELETE FROM bill_line_items WHERE bill_id = :bill_id"),
            {"bill_id": bill.id},
        )
        for i, item in enumerate(bill.line_items):
            self.conn.execute(
                text(
                    "INSERT INTO bill_line_items (bill_id, description, amount, item_type, sort_order) "
                    "VALUES (:bill_id, :description, :amount, :item_type, :sort_order)"
                ),
                {
                    "bill_id": bill.id,
                    "description": self.encryption.encrypt(item.description),
                    "amount": item.amount,
                    "item_type": item.item_type.value,
                    "sort_order": i,
                },
            )
        self.conn.commit()
        if bill.id is None:  # pragma: no cover
            raise ValueError("Cannot update bill without an id")
        result = self.get_by_id(bill.id)
        if result is None:
            raise RuntimeError(f"Failed to retrieve bill after update (id={bill.id})")
        return result

    @traced("bill_repo.update_pdf_path")
    def update_pdf_path(self, bill_id: int, pdf_path: str) -> None:
        self.conn.execute(
            text("UPDATE bills SET pdf_path = :pdf_path WHERE id = :id"),
            {"pdf_path": pdf_path, "id": bill_id},
        )
        self.conn.commit()

    @traced("bill_repo.update_recibo_pdf_path")
    def update_recibo_pdf_path(self, bill_id: int, recibo_pdf_path: str | None) -> None:
        self.conn.execute(
            text("UPDATE bills SET recibo_pdf_path = :recibo_pdf_path WHERE id = :id"),
            {"recibo_pdf_path": recibo_pdf_path, "id": bill_id},
        )
        self.conn.commit()

    @traced("bill_repo.update_status")
    def update_status(
        self,
        bill_id: int,
        expected_status: str,
        expected_status_updated_at: datetime | None,
        status: str,
        status_updated_at: datetime | None,
    ) -> bool:
        result = self.conn.execute(
            text(
                "UPDATE bills SET status = :status, status_updated_at = :status_updated_at "
                "WHERE id = :id AND status = :expected_status "
                "AND (status_updated_at = :expected_status_updated_at "
                "OR (status_updated_at IS NULL AND :expected_status_updated_at IS NULL)) "
                "AND deleted_at IS NULL"
            ),
            {
                "status": status,
                "status_updated_at": status_updated_at,
                "id": bill_id,
                "expected_status": expected_status,
                "expected_status_updated_at": expected_status_updated_at,
            },
        )
        self.conn.commit()
        return result.rowcount == 1

    @traced("bill_repo.update_status_and_clear_recibo")
    def update_status_and_clear_recibo(
        self,
        bill_id: int,
        expected_status: str,
        expected_status_updated_at: datetime | None,
        status: str,
        status_updated_at: datetime | None,
    ) -> tuple[bool, str | None]:
        params = {
            "id": bill_id,
            "expected_status": expected_status,
            "expected_status_updated_at": expected_status_updated_at,
            "status": status,
            "status_updated_at": status_updated_at,
        }
        lock = "" if self.conn.dialect.name == "sqlite" else " FOR UPDATE"
        try:
            row = (
                self.conn.execute(
                    text(
                        "SELECT recibo_pdf_path FROM bills WHERE id = :id "
                        "AND status = :expected_status "
                        "AND (status_updated_at = :expected_status_updated_at "
                        "OR (status_updated_at IS NULL AND :expected_status_updated_at IS NULL)) "
                        f"AND deleted_at IS NULL{lock}"
                    ),
                    params,
                )
                .mappings()
                .fetchone()
            )
            if row is None:
                self.conn.commit()
                return False, None
            result = self.conn.execute(
                text(
                    "UPDATE bills SET status = :status, status_updated_at = :status_updated_at, "
                    "recibo_pdf_path = NULL WHERE id = :id AND status = :expected_status "
                    "AND (status_updated_at = :expected_status_updated_at "
                    "OR (status_updated_at IS NULL AND :expected_status_updated_at IS NULL)) "
                    "AND deleted_at IS NULL"
                ),
                params,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        if result.rowcount != 1:
            return False, None
        return True, row["recibo_pdf_path"]

    @traced("bill_repo.restore_status_and_recibo")
    def restore_status_and_recibo(
        self,
        bill_id: int,
        expected_status: str,
        expected_status_updated_at: datetime | None,
        status: str,
        status_updated_at: datetime | None,
        recibo_pdf_path: str | None,
    ) -> bool:
        result = self.conn.execute(
            text(
                "UPDATE bills SET status = :status, status_updated_at = :status_updated_at, "
                "recibo_pdf_path = :recibo_pdf_path WHERE id = :id AND status = :expected_status "
                "AND (status_updated_at = :expected_status_updated_at "
                "OR (status_updated_at IS NULL AND :expected_status_updated_at IS NULL)) "
                "AND deleted_at IS NULL"
            ),
            {
                "id": bill_id,
                "expected_status": expected_status,
                "expected_status_updated_at": expected_status_updated_at,
                "status": status,
                "status_updated_at": status_updated_at,
                "recibo_pdf_path": recibo_pdf_path,
            },
        )
        self.conn.commit()
        return result.rowcount == 1

    @traced("bill_repo.replace_recibo_pdf_path_if_paid_version")
    def replace_recibo_pdf_path_if_paid_version(
        self,
        bill_id: int,
        expected_status_updated_at: datetime | None,
        expected_recibo_pdf_path: str | None,
        recibo_pdf_path: str,
    ) -> tuple[bool, str | None]:
        params = {
            "id": bill_id,
            "expected_status_updated_at": expected_status_updated_at,
            "expected_recibo_pdf_path": expected_recibo_pdf_path,
            "recibo_pdf_path": recibo_pdf_path,
        }
        try:
            result = self.conn.execute(
                text(
                    "UPDATE bills SET recibo_pdf_path = :recibo_pdf_path "
                    "WHERE id = :id AND status = 'paid' "
                    "AND (status_updated_at = :expected_status_updated_at "
                    "OR (status_updated_at IS NULL AND :expected_status_updated_at IS NULL)) "
                    "AND (recibo_pdf_path = :expected_recibo_pdf_path "
                    "OR (recibo_pdf_path IS NULL AND :expected_recibo_pdf_path IS NULL)) "
                    "AND deleted_at IS NULL"
                ),
                params,
            )
            if result.rowcount == 1:
                self.conn.commit()
                return True, expected_recibo_pdf_path
            row = (
                self.conn.execute(
                    text(
                        "SELECT recibo_pdf_path FROM bills WHERE id = :id AND status = 'paid' "
                        "AND (status_updated_at = :expected_status_updated_at "
                        "OR (status_updated_at IS NULL AND :expected_status_updated_at IS NULL)) "
                        "AND deleted_at IS NULL"
                    ),
                    params,
                )
                .mappings()
                .fetchone()
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return False, row["recibo_pdf_path"] if row is not None else None

    @traced("bill_repo.get_recibo_render_state")
    def get_recibo_render_state(
        self,
        bill_id: int,
        expected_status_updated_at: datetime | None,
    ) -> tuple[bool, str | None]:
        row = (
            self.conn.execute(
                text(
                    "SELECT recibo_pdf_path FROM bills WHERE id = :id AND status = 'paid' "
                    "AND (status_updated_at = :expected_status_updated_at "
                    "OR (status_updated_at IS NULL AND :expected_status_updated_at IS NULL)) "
                    "AND deleted_at IS NULL"
                ),
                {
                    "id": bill_id,
                    "expected_status_updated_at": expected_status_updated_at,
                },
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return False, None
        return True, row["recibo_pdf_path"]

    @traced("bill_repo.update_pdf_render_status")
    def update_pdf_render_status(self, bill_id: int, status: str | None) -> None:
        self.conn.execute(
            text("UPDATE bills SET pdf_render_status = :status, pdf_render_operation_id = NULL WHERE id = :id"),
            {"status": status, "id": bill_id},
        )
        self.conn.commit()

    @traced("bill_repo.begin_pdf_render")
    def begin_pdf_render(self, bill_id: int, operation_id: str) -> None:
        self.conn.execute(
            text(
                "UPDATE bills SET pdf_render_status = 'pending', pdf_render_operation_id = :operation_id "
                "WHERE id = :id AND deleted_at IS NULL"
            ),
            {"id": bill_id, "operation_id": operation_id},
        )
        self.conn.commit()

    @traced("bill_repo.claim_pending_pdf_render")
    def claim_pending_pdf_render(self, bill_id: int, operation_id: str) -> bool:
        result = self.conn.execute(
            text(
                "UPDATE bills SET pdf_render_operation_id = :operation_id "
                "WHERE id = :id AND pdf_render_status = 'pending' "
                "AND (pdf_render_operation_id IS NULL OR pdf_render_operation_id = :operation_id) "
                "AND deleted_at IS NULL"
            ),
            {"id": bill_id, "operation_id": operation_id},
        )
        self.conn.commit()
        return result.rowcount == 1

    @traced("bill_repo.finish_pdf_render")
    def finish_pdf_render(self, bill_id: int, operation_id: str, status: str | None) -> bool:
        result = self.conn.execute(
            text(
                "UPDATE bills SET pdf_render_status = :status, pdf_render_operation_id = NULL "
                "WHERE id = :id AND pdf_render_operation_id = :operation_id AND deleted_at IS NULL"
            ),
            {"id": bill_id, "operation_id": operation_id, "status": status},
        )
        self.conn.commit()
        return result.rowcount == 1

    @staticmethod
    def _editable_state(bill: Bill) -> tuple[object, ...]:
        return (
            bill.reference_month,
            bill.total_amount,
            bill.notes,
            bill.due_date,
            tuple((item.description, item.amount, item.item_type, item.sort_order) for item in bill.line_items),
        )

    @staticmethod
    def _restore_state(bill: Bill) -> tuple[object, ...]:
        return (
            *SQLAlchemyBillRepository._editable_state(bill),
            bill.pdf_path,
            bill.pdf_render_status,
        )

    @traced("bill_repo.restore_after_failed_render")
    def restore_after_failed_render(
        self,
        previous: Bill,
        expected_candidate: Bill,
        operation_id: str,
    ) -> bool:
        if previous.id is None:
            raise ValueError("Cannot restore bill without an id")
        params = {"id": previous.id, "operation_id": operation_id}
        select_bill = text("SELECT * FROM bills WHERE id = :id AND deleted_at IS NULL")
        if self.conn.dialect.name != "sqlite":
            select_bill = text("SELECT * FROM bills WHERE id = :id AND deleted_at IS NULL FOR UPDATE")
        try:
            if self.conn.dialect.name == "sqlite":
                # SQLite has no SELECT FOR UPDATE; this guarded no-op acquires its writer lock.
                self.conn.execute(
                    text(
                        "UPDATE bills SET pdf_render_operation_id = pdf_render_operation_id WHERE id = :id "
                        "AND pdf_render_operation_id = :operation_id AND deleted_at IS NULL"
                    ),
                    params,
                )
            row = (
                self.conn.execute(
                    select_bill,
                    params,
                )
                .mappings()
                .fetchone()
            )
            if row is None:
                self.conn.commit()
                return False
            if row["pdf_render_operation_id"] != operation_id:
                current = self._row_to_bill(row)
                self.conn.commit()
                return row["pdf_render_operation_id"] is None and self._restore_state(current) == self._restore_state(
                    previous
                )
            current = self._row_to_bill(row, lock=True)
            if current.mutation_revision != expected_candidate.mutation_revision:
                self.conn.commit()
                return False
            if self._editable_state(current) != self._editable_state(expected_candidate):
                self.conn.commit()
                return False

            result = self.conn.execute(
                text(
                    "UPDATE bills SET reference_month = :reference_month, "
                    "total_amount = :total_amount, notes = :notes, due_date = :due_date, "
                    "pdf_path = :pdf_path, pdf_render_status = :pdf_render_status, "
                    "pdf_render_operation_id = NULL, mutation_revision = mutation_revision + 1 "
                    "WHERE id = :id AND pdf_render_operation_id = :operation_id "
                    "AND mutation_revision = :mutation_revision AND deleted_at IS NULL"
                ),
                {
                    **params,
                    "reference_month": previous.reference_month,
                    "total_amount": previous.total_amount,
                    "notes": self.encryption.encrypt(previous.notes),
                    "due_date": previous.due_date,
                    "pdf_path": previous.pdf_path,
                    "pdf_render_status": previous.pdf_render_status,
                    "mutation_revision": expected_candidate.mutation_revision,
                },
            )
            if result.rowcount != 1:
                self.conn.rollback()
                return False
            self.conn.execute(
                text("DELETE FROM bill_line_items WHERE bill_id = :bill_id"),
                {"bill_id": previous.id},
            )
            for index, item in enumerate(previous.line_items):
                self.conn.execute(
                    text(
                        "INSERT INTO bill_line_items "
                        "(bill_id, description, amount, item_type, sort_order) "
                        "VALUES (:bill_id, :description, :amount, :item_type, :sort_order)"
                    ),
                    {
                        "bill_id": previous.id,
                        "description": self.encryption.encrypt(item.description),
                        "amount": item.amount,
                        "item_type": item.item_type.value,
                        "sort_order": index,
                    },
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return True

    @traced("bill_repo.get_pdf_render_state")
    def get_pdf_render_state(self, bill_id: int) -> tuple[str | None, str | None, str | None]:
        row = (
            self.conn.execute(
                text(
                    "SELECT pdf_render_operation_id, pdf_render_status, pdf_path FROM bills "
                    "WHERE id = :id AND deleted_at IS NULL"
                ),
                {"id": bill_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None, None, None
        return row["pdf_render_operation_id"], row["pdf_render_status"], row["pdf_path"]

    @traced("bill_repo.publish_pdf_render")
    def publish_pdf_render(
        self,
        bill_id: int,
        operation_id: str,
        pdf_path: str,
    ) -> tuple[bool, str | None]:
        params = {
            "id": bill_id,
            "operation_id": operation_id,
            "pdf_path": pdf_path,
        }
        lock = "" if self.conn.dialect.name == "sqlite" else " FOR UPDATE"
        try:
            row = (
                self.conn.execute(
                    text(
                        "SELECT pdf_path, pdf_render_operation_id FROM bills WHERE id = :id "
                        f"AND deleted_at IS NULL{lock}"
                    ),
                    params,
                )
                .mappings()
                .fetchone()
            )
            if row is None or row["pdf_render_operation_id"] != operation_id:
                self.conn.commit()
                return False, row["pdf_path"] if row is not None else None
            result = self.conn.execute(
                text(
                    "UPDATE bills SET pdf_path = :pdf_path, pdf_render_status = 'succeeded', "
                    "pdf_render_operation_id = NULL WHERE id = :id "
                    "AND pdf_render_operation_id = :operation_id AND deleted_at IS NULL"
                ),
                params,
            )
            if result.rowcount != 1:
                current = (
                    self.conn.execute(
                        text("SELECT pdf_path FROM bills WHERE id = :id AND deleted_at IS NULL"),
                        params,
                    )
                    .mappings()
                    .fetchone()
                )
                self.conn.commit()
                return False, current["pdf_path"] if current is not None else None
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return True, row["pdf_path"]

    @traced("bill_repo.fail_pending_pdf_render_without_operation")
    def fail_pending_pdf_render_without_operation(self, bill_id: int) -> bool:
        result = self.conn.execute(
            text(
                "UPDATE bills SET pdf_render_status = 'failed' "
                "WHERE id = :id AND pdf_render_status = 'pending' "
                "AND pdf_render_operation_id IS NULL AND deleted_at IS NULL"
            ),
            {"id": bill_id},
        )
        self.conn.commit()
        return result.rowcount == 1

    @traced("bill_repo.delete")
    def delete(self, bill_id: int) -> bool:
        result = self.conn.execute(
            text("UPDATE bills SET deleted_at = :deleted_at WHERE id = :id AND deleted_at IS NULL"),
            {"deleted_at": _now(), "id": bill_id},
        )
        self.conn.commit()
        return result.rowcount == 1

    @traced("bill_repo.delete_created")
    def delete_created(self, bill_id: int) -> bool:
        result = self.conn.execute(
            text("DELETE FROM bills WHERE id = :id"),
            {"id": bill_id},
        )
        self.conn.commit()
        return result.rowcount == 1
