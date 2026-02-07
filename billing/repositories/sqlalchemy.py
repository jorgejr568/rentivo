from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Connection, text

from billing.models.bill import Bill, BillLineItem
from billing.models.billing import Billing, BillingItem, ItemType
from billing.repositories.base import BillingRepository, BillRepository


class SQLAlchemyBillingRepository(BillingRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def create(self, billing: Billing) -> Billing:
        billing_uuid = str(uuid4())
        result = self.conn.execute(
            text(
                "INSERT INTO billings (name, description, pix_key, uuid) "
                "VALUES (:name, :description, :pix_key, :uuid)"
            ),
            {"name": billing.name, "description": billing.description,
             "pix_key": billing.pix_key, "uuid": billing_uuid},
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
        return self.get_by_id(billing_id)  # type: ignore[return-value]

    def get_by_id(self, billing_id: int) -> Billing | None:
        row = self.conn.execute(
            text("SELECT * FROM billings WHERE id = :id"),
            {"id": billing_id},
        ).mappings().fetchone()
        if row is None:
            return None
        items = self.conn.execute(
            text("SELECT * FROM billing_items WHERE billing_id = :billing_id ORDER BY sort_order"),
            {"billing_id": billing_id},
        ).mappings().fetchall()
        return Billing(
            id=row["id"],
            uuid=row["uuid"],
            name=row["name"],
            description=row["description"],
            pix_key=row["pix_key"],
            items=[
                BillingItem(
                    id=it["id"],
                    billing_id=it["billing_id"],
                    description=it["description"],
                    amount=it["amount"],
                    item_type=ItemType(it["item_type"]),
                    sort_order=it["sort_order"],
                )
                for it in items
            ],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_all(self) -> list[Billing]:
        rows = self.conn.execute(
            text("SELECT id FROM billings ORDER BY created_at DESC")
        ).mappings().fetchall()
        billings = []
        for row in rows:
            billing = self.get_by_id(row["id"])
            if billing:
                billings.append(billing)
        return billings

    def delete(self, billing_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM billing_items WHERE billing_id = :billing_id"),
            {"billing_id": billing_id},
        )
        self.conn.execute(
            text("DELETE FROM billings WHERE id = :id"),
            {"id": billing_id},
        )
        self.conn.commit()


class SQLAlchemyBillRepository(BillRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def create(self, bill: Bill) -> Bill:
        bill_uuid = str(uuid4())
        result = self.conn.execute(
            text(
                "INSERT INTO bills (billing_id, reference_month, total_amount, pdf_path, notes, uuid) "
                "VALUES (:billing_id, :reference_month, :total_amount, :pdf_path, :notes, :uuid)"
            ),
            {"billing_id": bill.billing_id, "reference_month": bill.reference_month,
             "total_amount": bill.total_amount, "pdf_path": bill.pdf_path,
             "notes": bill.notes, "uuid": bill_uuid},
        )
        bill_id = result.lastrowid
        for i, item in enumerate(bill.line_items):
            self.conn.execute(
                text(
                    "INSERT INTO bill_line_items (bill_id, description, amount, item_type, sort_order) "
                    "VALUES (:bill_id, :description, :amount, :item_type, :sort_order)"
                ),
                {"bill_id": bill_id, "description": item.description,
                 "amount": item.amount, "item_type": item.item_type, "sort_order": i},
            )
        self.conn.commit()
        return self.get_by_id(bill_id)  # type: ignore[return-value]

    def get_by_id(self, bill_id: int) -> Bill | None:
        row = self.conn.execute(
            text("SELECT * FROM bills WHERE id = :id"),
            {"id": bill_id},
        ).mappings().fetchone()
        if row is None:
            return None
        items = self.conn.execute(
            text("SELECT * FROM bill_line_items WHERE bill_id = :bill_id ORDER BY sort_order"),
            {"bill_id": bill_id},
        ).mappings().fetchall()
        return Bill(
            id=row["id"],
            uuid=row["uuid"],
            billing_id=row["billing_id"],
            reference_month=row["reference_month"],
            total_amount=row["total_amount"],
            line_items=[
                BillLineItem(
                    id=it["id"],
                    bill_id=it["bill_id"],
                    description=it["description"],
                    amount=it["amount"],
                    item_type=it["item_type"],
                    sort_order=it["sort_order"],
                )
                for it in items
            ],
            pdf_path=row["pdf_path"],
            notes=row["notes"],
            created_at=row["created_at"],
        )

    def list_by_billing(self, billing_id: int) -> list[Bill]:
        rows = self.conn.execute(
            text("SELECT id FROM bills WHERE billing_id = :billing_id ORDER BY reference_month DESC"),
            {"billing_id": billing_id},
        ).mappings().fetchall()
        bills = []
        for row in rows:
            bill = self.get_by_id(row["id"])
            if bill:
                bills.append(bill)
        return bills

    def update(self, bill: Bill) -> Bill:
        self.conn.execute(
            text(
                "UPDATE bills SET reference_month = :reference_month, "
                "total_amount = :total_amount, notes = :notes WHERE id = :id"
            ),
            {"reference_month": bill.reference_month, "total_amount": bill.total_amount,
             "notes": bill.notes, "id": bill.id},
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
                 "amount": item.amount, "item_type": item.item_type, "sort_order": i},
            )
        self.conn.commit()
        return self.get_by_id(bill.id)  # type: ignore[return-value]

    def update_pdf_path(self, bill_id: int, pdf_path: str) -> None:
        self.conn.execute(
            text("UPDATE bills SET pdf_path = :pdf_path WHERE id = :id"),
            {"pdf_path": pdf_path, "id": bill_id},
        )
        self.conn.commit()
