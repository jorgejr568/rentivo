from __future__ import annotations

from sqlalchemy import Connection, bindparam, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.encryption.base import EncryptionBackend
from rentivo.models.expense import Expense
from rentivo.observability import traced
from rentivo.repositories.base import ExpenseRepository
from rentivo.repositories.sqlalchemy._common import _now


class SQLAlchemyExpenseRepository(ExpenseRepository):
    def __init__(self, conn: Connection, encryption: EncryptionBackend) -> None:
        self.conn = conn
        self.encryption = encryption

    def _build_expenses(self, rows: list[RowMapping]) -> list[Expense]:
        if not rows:
            return []
        plaintexts = self.encryption.decrypt_many([row["description"] or "" for row in rows])
        return [
            Expense(
                id=row["id"],
                uuid=row["uuid"],
                billing_id=row["billing_id"],
                description=plaintext,
                amount=row["amount"],
                category=row["category"],
                incurred_on=row["incurred_on"],
                created_at=row["created_at"],
                deleted_at=row["deleted_at"],
            )
            for row, plaintext in zip(rows, plaintexts, strict=True)
        ]

    @traced("expense_repo.create")
    def create(self, expense: Expense) -> Expense:
        expense_uuid = str(ULID())
        now = _now()
        self.conn.execute(
            text(
                "INSERT INTO expenses (uuid, billing_id, description, amount, category, incurred_on, created_at) "
                "VALUES (:uuid, :billing_id, :description, :amount, :category, :incurred_on, :created_at)"
            ),
            {
                "uuid": expense_uuid,
                "billing_id": expense.billing_id,
                "description": self.encryption.encrypt(expense.description),
                "amount": expense.amount,
                "category": expense.category,
                "incurred_on": expense.incurred_on,
                "created_at": now,
            },
        )
        self.conn.commit()
        created = self.get_by_uuid(expense_uuid)
        if created is None:  # pragma: no cover
            raise RuntimeError(f"Failed to retrieve expense after create (uuid={expense_uuid})")
        return created

    @traced("expense_repo.get_by_uuid")
    def get_by_uuid(self, uuid: str) -> Expense | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM expenses WHERE uuid = :uuid AND deleted_at IS NULL"),
                {"uuid": uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._build_expenses([row])[0]

    @traced("expense_repo.list_by_billing")
    def list_by_billing(self, billing_id: int) -> list[Expense]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT * FROM expenses WHERE billing_id = :billing_id "
                    "AND deleted_at IS NULL ORDER BY incurred_on DESC, id DESC"
                ),
                {"billing_id": billing_id},
            )
            .mappings()
            .fetchall()
        )
        return self._build_expenses(list(rows))

    @traced("expense_repo.delete")
    def delete(self, expense_id: int) -> None:
        self.conn.execute(
            text("UPDATE expenses SET deleted_at = :deleted_at WHERE id = :id"),
            {"deleted_at": _now(), "id": expense_id},
        )
        self.conn.commit()

    @traced("expense_repo.total_for_billings")
    def total_for_billings(self, billing_ids: list[int]) -> int:
        if not billing_ids:
            return 0
        stmt = text(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE deleted_at IS NULL AND billing_id IN :billing_ids"
        ).bindparams(bindparam("billing_ids", expanding=True))
        return int(self.conn.execute(stmt, {"billing_ids": billing_ids}).scalar_one())
