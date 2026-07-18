from __future__ import annotations

from sqlalchemy import Connection, bindparam, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.encryption.base import EncryptionBackend
from rentivo.models.receipt import Receipt
from rentivo.observability import traced
from rentivo.repositories.base import ReceiptRepository
from rentivo.repositories.sqlalchemy._common import _now


class SQLAlchemyReceiptRepository(ReceiptRepository):
    def __init__(self, conn: Connection, encryption: EncryptionBackend) -> None:
        self.conn = conn
        self.encryption = encryption

    def _row_to_receipt(self, row: RowMapping) -> Receipt:
        return self._build_receipts([row])[0]

    def _build_receipts(self, rows: list[RowMapping]) -> list[Receipt]:
        if not rows:
            return []
        plaintexts = self.encryption.decrypt_many([row["filename"] or "" for row in rows])
        return [
            Receipt(
                id=row["id"],
                uuid=row["uuid"],
                bill_id=row["bill_id"],
                filename=plaintext,
                storage_key=row["storage_key"],
                content_type=row["content_type"],
                file_size=row["file_size"],
                sort_order=row["sort_order"],
                created_at=row["created_at"],
            )
            for row, plaintext in zip(rows, plaintexts, strict=True)
        ]

    @traced("receipt_repo.create")
    def create(self, receipt: Receipt) -> Receipt:
        receipt_uuid = str(ULID())
        now = _now()
        self.conn.execute(
            text(
                "INSERT INTO receipts (uuid, bill_id, filename, storage_key, content_type, "
                "file_size, sort_order, created_at) "
                "VALUES (:uuid, :bill_id, :filename, :storage_key, :content_type, "
                ":file_size, :sort_order, :created_at)"
            ),
            {
                "uuid": receipt_uuid,
                "bill_id": receipt.bill_id,
                "filename": self.encryption.encrypt(receipt.filename),
                "storage_key": receipt.storage_key,
                "content_type": receipt.content_type,
                "file_size": receipt.file_size,
                "sort_order": receipt.sort_order,
                "created_at": now,
            },
        )
        self.conn.commit()
        created = self.get_by_uuid(receipt_uuid)
        if created is None:
            raise RuntimeError(f"Failed to retrieve receipt after create (uuid={receipt_uuid})")
        return created

    @traced("receipt_repo.get_by_id")
    def get_by_id(self, receipt_id: int) -> Receipt | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM receipts WHERE id = :id"),
                {"id": receipt_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_receipt(row)

    @traced("receipt_repo.get_by_uuid")
    def get_by_uuid(self, uuid: str) -> Receipt | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM receipts WHERE uuid = :uuid"),
                {"uuid": uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_receipt(row)

    @traced("receipt_repo.list_by_bill")
    def list_by_bill(self, bill_id: int) -> list[Receipt]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM receipts WHERE bill_id = :bill_id ORDER BY sort_order, id"),
                {"bill_id": bill_id},
            )
            .mappings()
            .fetchall()
        )
        return self._build_receipts(list(rows))

    @traced("receipt_repo.delete")
    def delete(self, receipt_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        )
        self.conn.commit()

    @traced("receipt_repo.delete_many")
    def delete_many(self, receipt_ids: list[int]) -> int:
        if not receipt_ids:
            return 0
        statement = text("DELETE FROM receipts WHERE id IN :receipt_ids").bindparams(
            bindparam("receipt_ids", expanding=True)
        )
        result = self.conn.execute(statement, {"receipt_ids": receipt_ids})
        self.conn.commit()
        return result.rowcount

    @traced("receipt_repo.update_sort_orders")
    def update_sort_orders(self, updates: list[tuple[int, int]]) -> None:
        for receipt_id, sort_order in updates:
            self.conn.execute(
                text("UPDATE receipts SET sort_order = :sort_order WHERE id = :id"),
                {"sort_order": sort_order, "id": receipt_id},
            )
        self.conn.commit()
