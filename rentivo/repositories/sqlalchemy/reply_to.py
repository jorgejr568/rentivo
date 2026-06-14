from __future__ import annotations

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.encryption.base import EncryptionBackend
from rentivo.models.recipient import Recipient
from rentivo.observability import traced
from rentivo.repositories.base import RecipientRepository
from rentivo.repositories.sqlalchemy._common import _now, decrypt_columns


class SQLAlchemyReplyToRecipientRepository(RecipientRepository):
    """Reply-To contacts for a billing. Same shape and contract as
    ``SQLAlchemyRecipientRepository`` (the ``RecipientRepository`` ABC and the
    ``Recipient`` model are reused), backed by the separate ``billing_reply_to``
    table so the two contact lists never collide.
    """

    def __init__(self, conn: Connection, encryption: EncryptionBackend) -> None:
        self.conn = conn
        self.encryption = encryption

    def _build(self, rows: list[RowMapping]) -> list[Recipient]:
        if not rows:
            return []
        plaintexts = decrypt_columns(self.encryption, rows, ("name", "email"))
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

    @traced("reply_to_repo.list_by_billing")
    def list_by_billing(self, billing_id: int) -> list[Recipient]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM billing_reply_to WHERE billing_id = :bid ORDER BY sort_order, id"),
                {"bid": billing_id},
            )
            .mappings()
            .fetchall()
        )
        return self._build(list(rows))

    @traced("reply_to_repo.get_by_uuid")
    def get_by_uuid(self, uuid: str) -> Recipient | None:
        row = (
            self.conn.execute(text("SELECT * FROM billing_reply_to WHERE uuid = :u"), {"u": uuid}).mappings().fetchone()
        )
        if row is None:
            return None
        return self._build([row])[0]

    @traced("reply_to_repo.replace_for_billing")
    def replace_for_billing(self, billing_id: int, recipients: list[Recipient]) -> None:
        self.conn.execute(text("DELETE FROM billing_reply_to WHERE billing_id = :bid"), {"bid": billing_id})
        now = _now()
        for i, recipient in enumerate(recipients):
            self.conn.execute(
                text(
                    "INSERT INTO billing_reply_to (uuid, billing_id, name, email, sort_order, created_at) "
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
