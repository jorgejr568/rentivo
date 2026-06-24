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
        self.conn.commit()
        result = self.get_by_id(bill_id)
        if result is None:
            raise RuntimeError(f"Failed to retrieve bill after create (id={bill_id})")
        return result

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
            notes=notes,
            due_date=row["due_date"],
            status=row.get("status", "draft"),
            status_updated_at=row.get("status_updated_at"),
            pdf_render_status=row.get("pdf_render_status"),
            pix_provider=row.get("pix_provider"),
            pix_charge_id=row.get("pix_charge_id"),
            pix_txid=row.get("pix_txid"),
            pix_e2eid=row.get("pix_e2eid"),
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

    def _row_to_bill(self, row: RowMapping) -> Bill:
        items = list(
            self.conn.execute(
                text("SELECT * FROM bill_line_items WHERE bill_id = :bill_id ORDER BY sort_order"),
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
                "total_amount = :total_amount, notes = :notes, due_date = :due_date WHERE id = :id"
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

    @traced("bill_repo.update_status")
    def update_status(self, bill_id: int, status: str, status_updated_at: datetime) -> None:
        self.conn.execute(
            text("UPDATE bills SET status = :status, status_updated_at = :status_updated_at WHERE id = :id"),
            {"status": status, "status_updated_at": status_updated_at, "id": bill_id},
        )
        self.conn.commit()

    @traced("bill_repo.update_pdf_render_status")
    def update_pdf_render_status(self, bill_id: int, status: str | None) -> None:
        self.conn.execute(
            text("UPDATE bills SET pdf_render_status = :status WHERE id = :id"),
            {"status": status, "id": bill_id},
        )
        self.conn.commit()

    @traced("bill_repo.delete")
    def delete(self, bill_id: int) -> None:
        self.conn.execute(
            text("UPDATE bills SET deleted_at = :deleted_at WHERE id = :id"),
            {"deleted_at": _now(), "id": bill_id},
        )
        self.conn.commit()
