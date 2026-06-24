from __future__ import annotations

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.encryption.base import EncryptionBackend
from rentivo.models.billing_attachment import BillingAttachment
from rentivo.observability import traced
from rentivo.repositories.base import BillingAttachmentRepository
from rentivo.repositories.sqlalchemy._common import _now


class SQLAlchemyBillingAttachmentRepository(BillingAttachmentRepository):
    def __init__(self, conn: Connection, encryption: EncryptionBackend) -> None:
        self.conn = conn
        self.encryption = encryption

    def _row_to_attachment(self, row: RowMapping) -> BillingAttachment:
        return self._build_attachments([row])[0]

    def _build_attachments(self, rows: list[RowMapping]) -> list[BillingAttachment]:
        if not rows:
            return []
        # name + filename are both encrypted; decrypt all in one batched call.
        ciphertexts = [c for row in rows for c in (row["name"] or "", row["filename"] or "")]
        plain = iter(self.encryption.decrypt_many(ciphertexts))
        return [
            BillingAttachment(
                id=row["id"],
                uuid=row["uuid"],
                billing_id=row["billing_id"],
                name=next(plain),
                filename=next(plain),
                storage_key=row["storage_key"],
                content_type=row["content_type"],
                file_size=row["file_size"],
                sort_order=row["sort_order"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    @traced("billing_attachment_repo.create")
    def create(self, attachment: BillingAttachment) -> BillingAttachment:
        attachment_uuid = str(ULID())
        self.conn.execute(
            text(
                "INSERT INTO billing_attachments (uuid, billing_id, name, filename, "
                "storage_key, content_type, file_size, sort_order, created_at) "
                "VALUES (:uuid, :billing_id, :name, :filename, :storage_key, "
                ":content_type, :file_size, :sort_order, :created_at)"
            ),
            {
                "uuid": attachment_uuid,
                "billing_id": attachment.billing_id,
                "name": self.encryption.encrypt(attachment.name),
                "filename": self.encryption.encrypt(attachment.filename),
                "storage_key": attachment.storage_key,
                "content_type": attachment.content_type,
                "file_size": attachment.file_size,
                "sort_order": attachment.sort_order,
                "created_at": _now(),
            },
        )
        self.conn.commit()
        created = self.get_by_uuid(attachment_uuid)
        if created is None:
            raise RuntimeError(f"Failed to retrieve attachment after create (uuid={attachment_uuid})")
        return created

    @traced("billing_attachment_repo.get_by_id")
    def get_by_id(self, attachment_id: int) -> BillingAttachment | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM billing_attachments WHERE id = :id"),
                {"id": attachment_id},
            )
            .mappings()
            .fetchone()
        )
        return None if row is None else self._row_to_attachment(row)

    @traced("billing_attachment_repo.get_by_uuid")
    def get_by_uuid(self, uuid: str) -> BillingAttachment | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM billing_attachments WHERE uuid = :uuid"),
                {"uuid": uuid},
            )
            .mappings()
            .fetchone()
        )
        return None if row is None else self._row_to_attachment(row)

    @traced("billing_attachment_repo.list_by_billing")
    def list_by_billing(self, billing_id: int) -> list[BillingAttachment]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM billing_attachments WHERE billing_id = :billing_id ORDER BY sort_order, id"),
                {"billing_id": billing_id},
            )
            .mappings()
            .fetchall()
        )
        return self._build_attachments(list(rows))

    @traced("billing_attachment_repo.delete")
    def delete(self, attachment_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM billing_attachments WHERE id = :id"),
            {"id": attachment_id},
        )
        self.conn.commit()
