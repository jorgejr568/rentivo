from __future__ import annotations

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.encryption.base import EncryptionBackend
from rentivo.models.recipient import Recipient
from rentivo.repositories.base import RecipientRepository
from rentivo.repositories.sqlalchemy._common import _now


class SQLAlchemyRecipientRepository(RecipientRepository):
    def __init__(self, conn: Connection, encryption: EncryptionBackend) -> None:
        self.conn = conn
        self.encryption = encryption

    def _build(self, rows: list[RowMapping]) -> list[Recipient]:
        if not rows:
            return []
        plaintexts = iter(
            self.encryption.decrypt_many([v for row in rows for v in (row["name"] or "", row["email"] or "")])
        )
        return [
            Recipient(
                id=row["id"],
                uuid=row["uuid"],
                billing_id=row["billing_id"],
                name=next(plaintexts),
                email=next(plaintexts),
                sort_order=row["sort_order"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_by_billing(self, billing_id: int) -> list[Recipient]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM billing_recipients WHERE billing_id = :bid ORDER BY sort_order, id"),
                {"bid": billing_id},
            )
            .mappings()
            .fetchall()
        )
        return self._build(list(rows))

    def get_by_uuid(self, uuid: str) -> Recipient | None:
        row = (
            self.conn.execute(text("SELECT * FROM billing_recipients WHERE uuid = :u"), {"u": uuid})
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._build([row])[0]

    def replace_for_billing(self, billing_id: int, recipients: list[Recipient]) -> None:
        self.conn.execute(text("DELETE FROM billing_recipients WHERE billing_id = :bid"), {"bid": billing_id})
        now = _now()
        for i, recipient in enumerate(recipients):
            self.conn.execute(
                text(
                    "INSERT INTO billing_recipients (uuid, billing_id, name, email, sort_order, created_at) "
                    "VALUES (:uuid, :billing_id, :name, :email, :sort_order, :created_at)"
                ),
                {
                    "uuid": str(ULID()),
                    "billing_id": billing_id,
                    "name": self.encryption.encrypt(recipient.name),
                    "email": self.encryption.encrypt(recipient.email),
                    "sort_order": i,
                    "created_at": now,
                },
            )
        self.conn.commit()
