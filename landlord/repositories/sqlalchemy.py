from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from landlord.models.bill import Bill, BillLineItem
from landlord.models.billing import Billing, BillingItem, ItemType
from landlord.models.user import User
from landlord.repositories.base import BillingRepository, BillRepository, UserRepository

SP_TZ = ZoneInfo("America/Sao_Paulo")


def _now() -> datetime:
    return datetime.now(SP_TZ)


class SQLAlchemyBillingRepository(BillingRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def create(self, billing: Billing) -> Billing:
        billing_uuid = str(ULID())
        now = _now()
        result = self.conn.execute(
            text(
                "INSERT INTO billings (name, description, pix_key, uuid, created_at, updated_at) "
                "VALUES (:name, :description, :pix_key, :uuid, :created_at, :updated_at)"
            ),
            {"name": billing.name, "description": billing.description,
             "pix_key": billing.pix_key, "uuid": billing_uuid,
             "created_at": now, "updated_at": now},
        )
        billing_id = result.lastrowid
        for i, item in enumerate(billing.items):
            self.conn.execute(
                text(
                    "INSERT INTO billing_items (billing_id, description, amount, item_type, sort_order) "
                    "VALUES (:billing_id, :description, :amount, :item_type, :sort_order)"
                ),
                {"billing_id": billing_id, "description": item.description,
                 "amount": item.amount, "item_type": item.item_type.value, "sort_order": i},
            )
        self.conn.commit()
        result = self.get_by_id(billing_id)
        assert result is not None
        return result

    @staticmethod
    def _build_billing(row: RowMapping, item_rows: list[RowMapping]) -> Billing:
        return Billing(
            id=row["id"],
            uuid=row["uuid"],
            name=row["name"],
            description=row["description"],
            pix_key=row["pix_key"],
            items=[
                BillingItem(
                    id=item_row["id"],
                    billing_id=item_row["billing_id"],
                    description=item_row["description"],
                    amount=item_row["amount"],
                    item_type=ItemType(item_row["item_type"]),
                    sort_order=item_row["sort_order"],
                )
                for item_row in item_rows
            ],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"],
        )

    def _row_to_billing(self, row: RowMapping) -> Billing:
        items = self.conn.execute(
            text("SELECT * FROM billing_items WHERE billing_id = :billing_id ORDER BY sort_order"),
            {"billing_id": row["id"]},
        ).mappings().fetchall()
        return self._build_billing(row, list(items))

    def get_by_id(self, billing_id: int) -> Billing | None:
        row = self.conn.execute(
            text("SELECT * FROM billings WHERE id = :id AND deleted_at IS NULL"),
            {"id": billing_id},
        ).mappings().fetchone()
        if row is None:
            return None
        return self._row_to_billing(row)

    def get_by_uuid(self, uuid: str) -> Billing | None:
        row = self.conn.execute(
            text("SELECT * FROM billings WHERE uuid = :uuid AND deleted_at IS NULL"),
            {"uuid": uuid},
        ).mappings().fetchone()
        if row is None:
            return None
        return self._row_to_billing(row)

    def list_all(self) -> list[Billing]:
        rows = self.conn.execute(
            text("SELECT * FROM billings WHERE deleted_at IS NULL ORDER BY created_at DESC")
        ).mappings().fetchall()
        if not rows:
            return []
        billing_ids = [row["id"] for row in rows]
        placeholders = ", ".join(f":id{i}" for i in range(len(billing_ids)))
        params = {f"id{i}": bid for i, bid in enumerate(billing_ids)}
        all_items = self.conn.execute(
            text(f"SELECT * FROM billing_items WHERE billing_id IN ({placeholders}) ORDER BY sort_order"),
            params,
        ).mappings().fetchall()
        items_by_billing: dict[int, list[RowMapping]] = {}
        for item_row in all_items:
            items_by_billing.setdefault(item_row["billing_id"], []).append(item_row)
        return [
            self._build_billing(row, items_by_billing.get(row["id"], []))
            for row in rows
        ]

    def update(self, billing: Billing) -> Billing:
        self.conn.execute(
            text(
                "UPDATE billings SET name = :name, description = :description, "
                "pix_key = :pix_key, updated_at = :updated_at WHERE id = :id"
            ),
            {"name": billing.name, "description": billing.description,
             "pix_key": billing.pix_key, "updated_at": _now(), "id": billing.id},
        )
        self.conn.execute(
            text("DELETE FROM billing_items WHERE billing_id = :billing_id"),
            {"billing_id": billing.id},
        )
        for i, item in enumerate(billing.items):
            self.conn.execute(
                text(
                    "INSERT INTO billing_items (billing_id, description, amount, item_type, sort_order) "
                    "VALUES (:billing_id, :description, :amount, :item_type, :sort_order)"
                ),
                {"billing_id": billing.id, "description": item.description,
                 "amount": item.amount, "item_type": item.item_type.value, "sort_order": i},
            )
        self.conn.commit()
        assert billing.id is not None
        result = self.get_by_id(billing.id)
        assert result is not None
        return result

    def delete(self, billing_id: int) -> None:
        self.conn.execute(
            text("UPDATE billings SET deleted_at = :deleted_at WHERE id = :id"),
            {"deleted_at": _now(), "id": billing_id},
        )
        self.conn.commit()


class SQLAlchemyBillRepository(BillRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def create(self, bill: Bill) -> Bill:
        bill_uuid = str(ULID())
        result = self.conn.execute(
            text(
                "INSERT INTO bills (billing_id, reference_month, total_amount, pdf_path, notes, uuid, due_date, created_at) "
                "VALUES (:billing_id, :reference_month, :total_amount, :pdf_path, :notes, :uuid, :due_date, :created_at)"
            ),
            {"billing_id": bill.billing_id, "reference_month": bill.reference_month,
             "total_amount": bill.total_amount, "pdf_path": bill.pdf_path,
             "notes": bill.notes, "uuid": bill_uuid, "due_date": bill.due_date,
             "created_at": _now()},
        )
        bill_id = result.lastrowid
        for i, item in enumerate(bill.line_items):
            self.conn.execute(
                text(
                    "INSERT INTO bill_line_items (bill_id, description, amount, item_type, sort_order) "
                    "VALUES (:bill_id, :description, :amount, :item_type, :sort_order)"
                ),
                {"bill_id": bill_id, "description": item.description,
                 "amount": item.amount, "item_type": item.item_type.value, "sort_order": i},
            )
        self.conn.commit()
        result = self.get_by_id(bill_id)
        assert result is not None
        return result

    @staticmethod
    def _build_bill(row: RowMapping, item_rows: list[RowMapping]) -> Bill:
        return Bill(
            id=row["id"],
            uuid=row["uuid"],
            billing_id=row["billing_id"],
            reference_month=row["reference_month"],
            total_amount=row["total_amount"],
            line_items=[
                BillLineItem(
                    id=item_row["id"],
                    bill_id=item_row["bill_id"],
                    description=item_row["description"],
                    amount=item_row["amount"],
                    item_type=ItemType(item_row["item_type"]),
                    sort_order=item_row["sort_order"],
                )
                for item_row in item_rows
            ],
            pdf_path=row["pdf_path"],
            notes=row["notes"],
            due_date=row["due_date"],
            paid_at=row["paid_at"],
            created_at=row["created_at"],
            deleted_at=row["deleted_at"],
        )

    def _row_to_bill(self, row: RowMapping) -> Bill:
        items = self.conn.execute(
            text("SELECT * FROM bill_line_items WHERE bill_id = :bill_id ORDER BY sort_order"),
            {"bill_id": row["id"]},
        ).mappings().fetchall()
        return self._build_bill(row, list(items))

    def get_by_id(self, bill_id: int) -> Bill | None:
        row = self.conn.execute(
            text("SELECT * FROM bills WHERE id = :id AND deleted_at IS NULL"),
            {"id": bill_id},
        ).mappings().fetchone()
        if row is None:
            return None
        return self._row_to_bill(row)

    def get_by_uuid(self, uuid: str) -> Bill | None:
        row = self.conn.execute(
            text("SELECT * FROM bills WHERE uuid = :uuid AND deleted_at IS NULL"),
            {"uuid": uuid},
        ).mappings().fetchone()
        if row is None:
            return None
        return self._row_to_bill(row)

    def list_by_billing(self, billing_id: int) -> list[Bill]:
        rows = self.conn.execute(
            text("SELECT * FROM bills WHERE billing_id = :billing_id AND deleted_at IS NULL ORDER BY reference_month DESC"),
            {"billing_id": billing_id},
        ).mappings().fetchall()
        if not rows:
            return []
        bill_ids = [row["id"] for row in rows]
        placeholders = ", ".join(f":id{i}" for i in range(len(bill_ids)))
        params = {f"id{i}": bid for i, bid in enumerate(bill_ids)}
        all_items = self.conn.execute(
            text(f"SELECT * FROM bill_line_items WHERE bill_id IN ({placeholders}) ORDER BY sort_order"),
            params,
        ).mappings().fetchall()
        items_by_bill: dict[int, list[RowMapping]] = {}
        for item_row in all_items:
            items_by_bill.setdefault(item_row["bill_id"], []).append(item_row)
        return [
            self._build_bill(row, items_by_bill.get(row["id"], []))
            for row in rows
        ]

    def update(self, bill: Bill) -> Bill:
        self.conn.execute(
            text(
                "UPDATE bills SET reference_month = :reference_month, "
                "total_amount = :total_amount, notes = :notes, due_date = :due_date WHERE id = :id"
            ),
            {"reference_month": bill.reference_month, "total_amount": bill.total_amount,
             "notes": bill.notes, "due_date": bill.due_date, "id": bill.id},
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
                {"bill_id": bill.id, "description": item.description,
                 "amount": item.amount, "item_type": item.item_type.value, "sort_order": i},
            )
        self.conn.commit()
        assert bill.id is not None
        result = self.get_by_id(bill.id)
        assert result is not None
        return result

    def update_pdf_path(self, bill_id: int, pdf_path: str) -> None:
        self.conn.execute(
            text("UPDATE bills SET pdf_path = :pdf_path WHERE id = :id"),
            {"pdf_path": pdf_path, "id": bill_id},
        )
        self.conn.commit()

    def update_paid_at(self, bill_id: int, paid_at: datetime | None) -> None:
        self.conn.execute(
            text("UPDATE bills SET paid_at = :paid_at WHERE id = :id"),
            {"paid_at": paid_at, "id": bill_id},
        )
        self.conn.commit()

    def delete(self, bill_id: int) -> None:
        self.conn.execute(
            text("UPDATE bills SET deleted_at = :deleted_at WHERE id = :id"),
            {"deleted_at": _now(), "id": bill_id},
        )
        self.conn.commit()


class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def create(self, user: User) -> User:
        result = self.conn.execute(
            text(
                "INSERT INTO users (username, password_hash, created_at) "
                "VALUES (:username, :password_hash, :created_at)"
            ),
            {"username": user.username, "password_hash": user.password_hash,
             "created_at": _now()},
        )
        self.conn.commit()
        result = self.get_by_username(user.username)
        assert result is not None
        return result

    def get_by_username(self, username: str) -> User | None:
        row = self.conn.execute(
            text("SELECT * FROM users WHERE username = :username"),
            {"username": username},
        ).mappings().fetchone()
        if row is None:
            return None
        return User(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
        )

    def list_all(self) -> list[User]:
        rows = self.conn.execute(
            text("SELECT * FROM users ORDER BY created_at DESC")
        ).mappings().fetchall()
        return [
            User(
                id=row["id"],
                username=row["username"],
                password_hash=row["password_hash"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def update_password_hash(self, username: str, password_hash: str) -> None:
        self.conn.execute(
            text("UPDATE users SET password_hash = :password_hash WHERE username = :username"),
            {"password_hash": password_hash, "username": username},
        )
        self.conn.commit()
