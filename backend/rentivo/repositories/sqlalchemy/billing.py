from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Connection, bindparam, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.encryption.base import EncryptionBackend
from rentivo.models.billing import Billing, BillingItem, ItemType
from rentivo.observability import traced
from rentivo.repositories.base import BillingRepository
from rentivo.repositories.sqlalchemy._common import _group_rows_by, _now


class SQLAlchemyBillingRepository(BillingRepository):
    def __init__(self, conn: Connection, encryption: EncryptionBackend) -> None:
        self.conn = conn
        self.encryption = encryption

    @traced("billing_repo.create")
    def create(self, billing: Billing) -> Billing:
        billing_uuid = str(ULID())
        now = _now()
        result = self.conn.execute(
            text(
                "INSERT INTO billings (name, description, pix_key, pix_merchant_name, pix_merchant_city, "
                "uuid, owner_type, owner_id, created_at, updated_at) "
                "VALUES (:name, :description, :pix_key, :pix_merchant_name, :pix_merchant_city, "
                ":uuid, :owner_type, :owner_id, :created_at, :updated_at)"
            ),
            {
                "name": self.encryption.encrypt(billing.name),
                "description": self.encryption.encrypt(billing.description),
                "pix_key": self.encryption.encrypt(billing.pix_key),
                "pix_merchant_name": self.encryption.encrypt(billing.pix_merchant_name),
                "pix_merchant_city": self.encryption.encrypt(billing.pix_merchant_city),
                "uuid": billing_uuid,
                "owner_type": billing.owner_type,
                "owner_id": billing.owner_id,
                "created_at": now,
                "updated_at": now,
            },
        )
        billing_id = result.lastrowid
        for i, item in enumerate(billing.items):
            self.conn.execute(
                text(
                    "INSERT INTO billing_items (billing_id, uuid, description, amount, item_type, sort_order) "
                    "VALUES (:billing_id, :uuid, :description, :amount, :item_type, :sort_order)"
                ),
                {
                    "billing_id": billing_id,
                    "uuid": item.uuid,
                    "description": self.encryption.encrypt(item.description),
                    "amount": item.amount,
                    "item_type": item.item_type.value,
                    "sort_order": i,
                },
            )
        self.conn.commit()
        result = self.get_by_id(billing_id)
        if result is None:
            raise RuntimeError(f"Failed to retrieve billing after create (id={billing_id})")
        return result

    def _build_billing(
        self,
        row: RowMapping,
        item_rows: list[RowMapping],
        plaintexts: Iterator[str],
    ) -> Billing:
        # Consumes plaintexts in the order produced by ``_gather_billing_ciphertexts``:
        # name, description, pix_key, pix_merchant_name, pix_merchant_city, then one per item.
        name = next(plaintexts)
        description = next(plaintexts)
        pix_key = next(plaintexts)
        pix_merchant_name = next(plaintexts)
        pix_merchant_city = next(plaintexts)
        items = [
            BillingItem(
                id=item_row["id"],
                billing_id=item_row["billing_id"],
                uuid=item_row["uuid"],
                description=next(plaintexts),
                amount=item_row["amount"],
                item_type=ItemType(item_row["item_type"]),
                sort_order=item_row["sort_order"],
            )
            for item_row in item_rows
        ]
        return Billing(
            id=row["id"],
            uuid=row["uuid"],
            name=name,
            description=description,
            pix_key=pix_key,
            pix_merchant_name=pix_merchant_name,
            pix_merchant_city=pix_merchant_city,
            owner_type=row.get("owner_type", "user"),
            owner_id=row.get("owner_id", 0),
            items=items,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"],
        )

    @staticmethod
    def _gather_billing_ciphertexts(
        rows: list[RowMapping],
        items_by_billing: dict[int, list[RowMapping]],
    ) -> list[str]:
        ciphertexts: list[str] = []
        for row in rows:
            ciphertexts.append(row["name"] or "")
            ciphertexts.append(row["description"] or "")
            ciphertexts.append(row["pix_key"] or "")
            ciphertexts.append(row.get("pix_merchant_name", "") or "")
            ciphertexts.append(row.get("pix_merchant_city", "") or "")
            for item_row in items_by_billing.get(row["id"], []):
                ciphertexts.append(item_row["description"] or "")
        return ciphertexts

    def _build_billings(self, rows: list[RowMapping], items_by_billing: dict[int, list[RowMapping]]) -> list[Billing]:
        """Decrypt every encrypted cell across ``rows`` (and their items) in one
        batched call, then assemble the models."""
        ciphertexts = self._gather_billing_ciphertexts(rows, items_by_billing)
        plaintexts = iter(self.encryption.decrypt_many(ciphertexts))
        return [self._build_billing(row, items_by_billing.get(row["id"], []), plaintexts) for row in rows]

    def _row_to_billing(self, row: RowMapping) -> Billing:
        items = list(
            self.conn.execute(
                text("SELECT * FROM billing_items WHERE billing_id = :billing_id ORDER BY sort_order"),
                {"billing_id": row["id"]},
            )
            .mappings()
            .fetchall()
        )
        return self._build_billings([row], {row["id"]: items})[0]

    @traced("billing_repo.get_by_id")
    def get_by_id(self, billing_id: int) -> Billing | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM billings WHERE id = :id AND deleted_at IS NULL"),
                {"id": billing_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_billing(row)

    @traced("billing_repo.get_by_uuid")
    def get_by_uuid(self, uuid: str) -> Billing | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM billings WHERE uuid = :uuid AND deleted_at IS NULL"),
                {"uuid": uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_billing(row)

    @traced("billing_repo.list_all")
    def list_all(self) -> list[Billing]:
        rows = (
            self.conn.execute(text("SELECT * FROM billings WHERE deleted_at IS NULL ORDER BY created_at DESC"))
            .mappings()
            .fetchall()
        )
        return self._build_billings_from_rows(rows)

    @traced("billing_repo.list_for_user")
    def list_for_user(self, user_id: int) -> list[Billing]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT * FROM billings WHERE deleted_at IS NULL AND ("
                    "(owner_type = 'user' AND owner_id = :uid) OR "
                    "(owner_type = 'organization' AND owner_id IN "
                    "(SELECT organization_id FROM organization_members WHERE user_id = :uid))"
                    ") ORDER BY created_at DESC"
                ),
                {"uid": user_id},
            )
            .mappings()
            .fetchall()
        )
        return self._build_billings_from_rows(rows)

    def _build_billings_from_rows(self, rows: list[RowMapping]) -> list[Billing]:
        if not rows:
            return []
        billing_ids = [row["id"] for row in rows]
        stmt = text("SELECT * FROM billing_items WHERE billing_id IN :billing_ids ORDER BY sort_order").bindparams(
            bindparam("billing_ids", expanding=True)
        )
        all_items = self.conn.execute(stmt, {"billing_ids": billing_ids}).mappings().fetchall()
        items_by_billing = _group_rows_by(all_items, "billing_id")
        return self._build_billings(rows, items_by_billing)

    @traced("billing_repo.update")
    def update(self, billing: Billing) -> Billing:
        self.conn.execute(
            text(
                "UPDATE billings SET name = :name, description = :description, "
                "pix_key = :pix_key, pix_merchant_name = :pix_merchant_name, "
                "pix_merchant_city = :pix_merchant_city, updated_at = :updated_at WHERE id = :id"
            ),
            {
                "name": self.encryption.encrypt(billing.name),
                "description": self.encryption.encrypt(billing.description),
                "pix_key": self.encryption.encrypt(billing.pix_key),
                "pix_merchant_name": self.encryption.encrypt(billing.pix_merchant_name),
                "pix_merchant_city": self.encryption.encrypt(billing.pix_merchant_city),
                "updated_at": _now(),
                "id": billing.id,
            },
        )
        self.conn.execute(
            text("DELETE FROM billing_items WHERE billing_id = :billing_id"),
            {"billing_id": billing.id},
        )
        for i, item in enumerate(billing.items):
            self.conn.execute(
                text(
                    "INSERT INTO billing_items (billing_id, uuid, description, amount, item_type, sort_order) "
                    "VALUES (:billing_id, :uuid, :description, :amount, :item_type, :sort_order)"
                ),
                {
                    "billing_id": billing.id,
                    "uuid": item.uuid,
                    "description": self.encryption.encrypt(item.description),
                    "amount": item.amount,
                    "item_type": item.item_type.value,
                    "sort_order": i,
                },
            )
        self.conn.commit()
        if billing.id is None:  # pragma: no cover
            raise ValueError("Cannot update billing without an id")
        result = self.get_by_id(billing.id)
        if result is None:
            raise RuntimeError(f"Failed to retrieve billing after update (id={billing.id})")
        return result

    @traced("billing_repo.delete")
    def delete(self, billing_id: int) -> None:
        self.conn.execute(
            text("UPDATE billings SET deleted_at = :deleted_at WHERE id = :id"),
            {"deleted_at": _now(), "id": billing_id},
        )
        self.conn.commit()

    @traced("billing_repo.transfer_owner")
    def transfer_owner(self, billing_id: int, owner_type: str, owner_id: int) -> None:
        self.conn.execute(
            text(
                "UPDATE billings SET owner_type = :owner_type, owner_id = :owner_id, "
                "updated_at = :updated_at WHERE id = :id"
            ),
            {"owner_type": owner_type, "owner_id": owner_id, "updated_at": _now(), "id": billing_id},
        )
        self.conn.commit()

    @traced("billing_repo.transfer_owner_if_current")
    def transfer_owner_if_current(
        self,
        billing_id: int,
        expected_owner_type: str,
        expected_owner_id: int,
        owner_type: str,
        owner_id: int,
    ) -> bool:
        result = self.conn.execute(
            text(
                "UPDATE billings SET owner_type = :owner_type, owner_id = :owner_id, "
                "updated_at = :updated_at WHERE id = :id AND deleted_at IS NULL "
                "AND owner_type = :expected_owner_type AND owner_id = :expected_owner_id"
            ),
            {
                "owner_type": owner_type,
                "owner_id": owner_id,
                "updated_at": _now(),
                "id": billing_id,
                "expected_owner_type": expected_owner_type,
                "expected_owner_id": expected_owner_id,
            },
        )
        self.conn.commit()
        return result.rowcount == 1
