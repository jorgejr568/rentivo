from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.constants import SP_TZ
from rentivo.encryption.base import EncryptionBackend
from rentivo.models.audit_log import AuditLog
from rentivo.models.invite import Invite
from rentivo.models.known_device import KnownDevice
from rentivo.models.mfa import RecoveryCode, UserPasskey, UserTOTP
from rentivo.models.password_reset_token import PasswordResetToken
from rentivo.models.receipt import Receipt
from rentivo.models.theme import Theme
from rentivo.repositories.base import (
    AuditLogRepository,
    InviteRepository,
    KnownDeviceRepository,
    MFATOTPRepository,
    PasskeyRepository,
    PasswordResetTokenRepository,
    ReceiptRepository,
    RecoveryCodeRepository,
    ThemeRepository,
)


def _now() -> datetime:
    return datetime.now(SP_TZ)


class SQLAlchemyInviteRepository(InviteRepository):
    def __init__(self, conn: Connection, encryption: EncryptionBackend) -> None:
        self.conn = conn
        self.encryption = encryption

    def _row_to_invite(self, row: RowMapping) -> Invite:
        return Invite(
            id=row["id"],
            uuid=row["uuid"],
            organization_id=row["organization_id"],
            organization_name=row.get("org_name", ""),
            invited_user_id=row["invited_user_id"],
            invited_email=self.encryption.decrypt(row.get("invited_email", "") or ""),
            invited_by_user_id=row["invited_by_user_id"],
            invited_by_email=self.encryption.decrypt(row.get("invited_by_email", "") or ""),
            role=row["role"],
            status=row["status"],
            enforce_mfa=bool(row.get("enforce_mfa", False)),
            created_at=row["created_at"],
            responded_at=row.get("responded_at"),
        )

    def create(self, invite: Invite) -> Invite:
        invite_uuid = str(ULID())
        now = _now()
        self.conn.execute(
            text(
                "INSERT INTO invites (uuid, organization_id, invited_user_id, "
                "invited_by_user_id, role, status, created_at) "
                "VALUES (:uuid, :org_id, :invited_user_id, :invited_by_user_id, "
                ":role, :status, :created_at)"
            ),
            {
                "uuid": invite_uuid,
                "org_id": invite.organization_id,
                "invited_user_id": invite.invited_user_id,
                "invited_by_user_id": invite.invited_by_user_id,
                "role": invite.role,
                "status": invite.status,
                "created_at": now,
            },
        )
        self.conn.commit()
        created = self.get_by_uuid(invite_uuid)
        if created is None:
            raise RuntimeError("Failed to retrieve invite after create")
        return created

    def get_by_uuid(self, uuid: str) -> Invite | None:
        row = (
            self.conn.execute(
                text(
                    "SELECT i.*, o.name AS org_name, o.enforce_mfa, "
                    "u1.email AS invited_email, u2.email AS invited_by_email "
                    "FROM invites i "
                    "JOIN organizations o ON i.organization_id = o.id "
                    "JOIN users u1 ON i.invited_user_id = u1.id "
                    "JOIN users u2 ON i.invited_by_user_id = u2.id "
                    "WHERE i.uuid = :uuid"
                ),
                {"uuid": uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_invite(row)

    def list_pending_for_user(self, user_id: int) -> list[Invite]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT i.*, o.name AS org_name, o.enforce_mfa, "
                    "u1.email AS invited_email, u2.email AS invited_by_email "
                    "FROM invites i "
                    "JOIN organizations o ON i.organization_id = o.id "
                    "JOIN users u1 ON i.invited_user_id = u1.id "
                    "JOIN users u2 ON i.invited_by_user_id = u2.id "
                    "WHERE i.invited_user_id = :uid AND i.status = 'pending' "
                    "ORDER BY i.created_at DESC"
                ),
                {"uid": user_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_invite(row) for row in rows]

    def list_by_organization(self, org_id: int) -> list[Invite]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT i.*, o.name AS org_name, o.enforce_mfa, "
                    "u1.email AS invited_email, u2.email AS invited_by_email "
                    "FROM invites i "
                    "JOIN organizations o ON i.organization_id = o.id "
                    "JOIN users u1 ON i.invited_user_id = u1.id "
                    "JOIN users u2 ON i.invited_by_user_id = u2.id "
                    "WHERE i.organization_id = :org_id "
                    "ORDER BY i.created_at DESC"
                ),
                {"org_id": org_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_invite(row) for row in rows]

    def update_status(self, invite_id: int, status: str) -> None:
        self.conn.execute(
            text("UPDATE invites SET status = :status, responded_at = :responded_at WHERE id = :id"),
            {"status": status, "responded_at": _now(), "id": invite_id},
        )
        self.conn.commit()

    def count_pending_for_user(self, user_id: int) -> int:
        result = (
            self.conn.execute(
                text("SELECT COUNT(*) AS cnt FROM invites WHERE invited_user_id = :uid AND status = 'pending'"),
                {"uid": user_id},
            )
            .mappings()
            .fetchone()
        )
        return result["cnt"] if result else 0

    def has_pending_invite(self, org_id: int, user_id: int) -> bool:
        result = (
            self.conn.execute(
                text(
                    "SELECT COUNT(*) AS cnt FROM invites "
                    "WHERE organization_id = :org_id AND invited_user_id = :uid "
                    "AND status = 'pending'"
                ),
                {"org_id": org_id, "uid": user_id},
            )
            .mappings()
            .fetchone()
        )
        return (result["cnt"] if result else 0) > 0


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

    def delete(self, receipt_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        )
        self.conn.commit()

    def update_sort_orders(self, updates: list[tuple[int, int]]) -> None:
        for receipt_id, sort_order in updates:
            self.conn.execute(
                text("UPDATE receipts SET sort_order = :sort_order WHERE id = :id"),
                {"sort_order": sort_order, "id": receipt_id},
            )
        self.conn.commit()


class SQLAlchemyAuditLogRepository(AuditLogRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row_to_audit_log(row: RowMapping) -> AuditLog:
        import json

        previous_state = row["previous_state"]
        if isinstance(previous_state, str):
            previous_state = json.loads(previous_state)
        new_state = row["new_state"]
        if isinstance(new_state, str):
            new_state = json.loads(new_state)
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return AuditLog(
            id=row["id"],
            uuid=row["uuid"],
            event_type=row["event_type"],
            actor_id=row["actor_id"],
            actor_username=row["actor_username"],
            source=row["source"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            entity_uuid=row["entity_uuid"],
            previous_state=previous_state,
            new_state=new_state,
            metadata=metadata,
            created_at=row["created_at"],
        )

    def create(self, audit_log: AuditLog) -> AuditLog:
        import json

        audit_uuid = str(ULID())
        now = _now()
        self.conn.execute(
            text(
                "INSERT INTO audit_logs (uuid, event_type, actor_id, actor_username, "
                "source, entity_type, entity_id, entity_uuid, previous_state, "
                "new_state, metadata, created_at) "
                "VALUES (:uuid, :event_type, :actor_id, :actor_username, "
                ":source, :entity_type, :entity_id, :entity_uuid, :previous_state, "
                ":new_state, :metadata, :created_at)"
            ),
            {
                "uuid": audit_uuid,
                "event_type": audit_log.event_type,
                "actor_id": audit_log.actor_id,
                "actor_username": audit_log.actor_username,
                "source": audit_log.source,
                "entity_type": audit_log.entity_type,
                "entity_id": audit_log.entity_id,
                "entity_uuid": audit_log.entity_uuid,
                "previous_state": json.dumps(audit_log.previous_state)
                if audit_log.previous_state is not None
                else None,
                "new_state": json.dumps(audit_log.new_state) if audit_log.new_state is not None else None,
                "metadata": json.dumps(audit_log.metadata),
                "created_at": now,
            },
        )
        self.conn.commit()

        row = (
            self.conn.execute(
                text("SELECT * FROM audit_logs WHERE uuid = :uuid"),
                {"uuid": audit_uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            raise RuntimeError(f"Failed to retrieve audit log after create (uuid={audit_uuid})")
        return self._row_to_audit_log(row)

    def list_by_entity(self, entity_type: str, entity_id: int) -> list[AuditLog]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT * FROM audit_logs "
                    "WHERE entity_type = :entity_type AND entity_id = :entity_id "
                    "ORDER BY created_at DESC"
                ),
                {"entity_type": entity_type, "entity_id": entity_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_audit_log(row) for row in rows]

    def list_by_actor(self, actor_id: int, limit: int = 50) -> list[AuditLog]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM audit_logs WHERE actor_id = :actor_id ORDER BY created_at DESC LIMIT :limit"),
                {"actor_id": actor_id, "limit": limit},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_audit_log(row) for row in rows]

    def list_recent(self, limit: int = 50) -> list[AuditLog]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT :limit"),
                {"limit": limit},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_audit_log(row) for row in rows]


class SQLAlchemyMFATOTPRepository(MFATOTPRepository):
    def __init__(self, conn: Connection, encryption: EncryptionBackend) -> None:
        self.conn = conn
        self.encryption = encryption

    def _row_to_totp(self, row: RowMapping) -> UserTOTP:
        return UserTOTP(
            id=row["id"],
            user_id=row["user_id"],
            secret=self.encryption.decrypt(row["secret"]),
            confirmed=bool(row["confirmed"]),
            created_at=row["created_at"],
            confirmed_at=row.get("confirmed_at"),
        )

    def get_by_user_id(self, user_id: int) -> UserTOTP | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM user_totp WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_totp(row)

    def create(self, totp: UserTOTP) -> UserTOTP:
        self.conn.execute(
            text(
                "INSERT INTO user_totp (user_id, secret, confirmed, created_at) "
                "VALUES (:user_id, :secret, :confirmed, :created_at)"
            ),
            {
                "user_id": totp.user_id,
                "secret": self.encryption.encrypt(totp.secret),
                "confirmed": totp.confirmed,
                "created_at": _now(),
            },
        )
        self.conn.commit()
        result = self.get_by_user_id(totp.user_id)
        if result is None:
            raise RuntimeError("Failed to retrieve TOTP after create")
        return result

    def confirm(self, user_id: int) -> None:
        self.conn.execute(
            text("UPDATE user_totp SET confirmed = 1, confirmed_at = :now WHERE user_id = :user_id"),
            {"now": _now(), "user_id": user_id},
        )
        self.conn.commit()

    def delete_by_user_id(self, user_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM user_totp WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        self.conn.commit()


class SQLAlchemyRecoveryCodeRepository(RecoveryCodeRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row_to_code(row: RowMapping) -> RecoveryCode:
        return RecoveryCode(
            id=row["id"],
            user_id=row["user_id"],
            code_hash=row["code_hash"],
            used_at=row.get("used_at"),
            created_at=row["created_at"],
        )

    def create_batch(self, user_id: int, code_hashes: list[str]) -> None:
        now = _now()
        for code_hash in code_hashes:
            self.conn.execute(
                text(
                    "INSERT INTO user_recovery_codes (user_id, code_hash, created_at) "
                    "VALUES (:user_id, :code_hash, :created_at)"
                ),
                {"user_id": user_id, "code_hash": code_hash, "created_at": now},
            )
        self.conn.commit()

    def list_unused_by_user(self, user_id: int) -> list[RecoveryCode]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM user_recovery_codes WHERE user_id = :user_id AND used_at IS NULL ORDER BY id"),
                {"user_id": user_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_code(row) for row in rows]

    def mark_used(self, code_id: int) -> None:
        self.conn.execute(
            text("UPDATE user_recovery_codes SET used_at = :now WHERE id = :id"),
            {"now": _now(), "id": code_id},
        )
        self.conn.commit()

    def delete_all_by_user(self, user_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM user_recovery_codes WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        self.conn.commit()


class SQLAlchemyPasskeyRepository(PasskeyRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row_to_passkey(row: RowMapping) -> UserPasskey:
        return UserPasskey(
            id=row["id"],
            uuid=row["uuid"],
            user_id=row["user_id"],
            credential_id=row["credential_id"],
            public_key=row["public_key"],
            sign_count=row["sign_count"],
            name=row["name"],
            transports=row.get("transports"),
            created_at=row["created_at"],
            last_used_at=row.get("last_used_at"),
        )

    def create(self, passkey: UserPasskey) -> UserPasskey:
        passkey_uuid = str(ULID())
        now = _now()
        self.conn.execute(
            text(
                "INSERT INTO user_passkeys (uuid, user_id, credential_id, public_key, "
                "sign_count, name, transports, created_at) "
                "VALUES (:uuid, :user_id, :credential_id, :public_key, "
                ":sign_count, :name, :transports, :created_at)"
            ),
            {
                "uuid": passkey_uuid,
                "user_id": passkey.user_id,
                "credential_id": passkey.credential_id,
                "public_key": passkey.public_key,
                "sign_count": passkey.sign_count,
                "name": passkey.name,
                "transports": passkey.transports,
                "created_at": now,
            },
        )
        self.conn.commit()
        created = self.get_by_uuid(passkey_uuid)
        if created is None:
            raise RuntimeError("Failed to retrieve passkey after create")
        return created

    def get_by_uuid(self, uuid: str) -> UserPasskey | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM user_passkeys WHERE uuid = :uuid"),
                {"uuid": uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_passkey(row)

    def get_by_credential_id(self, credential_id: str) -> UserPasskey | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM user_passkeys WHERE credential_id = :cid"),
                {"cid": credential_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_passkey(row)

    def list_by_user(self, user_id: int) -> list[UserPasskey]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM user_passkeys WHERE user_id = :user_id ORDER BY created_at"),
                {"user_id": user_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_passkey(row) for row in rows]

    def update_sign_count(self, passkey_id: int, sign_count: int) -> None:
        self.conn.execute(
            text("UPDATE user_passkeys SET sign_count = :sign_count WHERE id = :id"),
            {"sign_count": sign_count, "id": passkey_id},
        )
        self.conn.commit()

    def update_last_used(self, passkey_id: int) -> None:
        self.conn.execute(
            text("UPDATE user_passkeys SET last_used_at = :now WHERE id = :id"),
            {"now": _now(), "id": passkey_id},
        )
        self.conn.commit()

    def delete(self, passkey_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM user_passkeys WHERE id = :id"),
            {"id": passkey_id},
        )
        self.conn.commit()


class SQLAlchemyThemeRepository(ThemeRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row_to_theme(row: RowMapping) -> Theme:
        return Theme(
            id=row["id"],
            uuid=row["uuid"],
            owner_type=row["owner_type"],
            owner_id=row["owner_id"],
            name=row["name"],
            header_font=row["header_font"],
            text_font=row["text_font"],
            primary=row["primary_color"],
            primary_light=row["primary_light"],
            secondary=row["secondary"],
            secondary_dark=row["secondary_dark"],
            text_color=row["text_color"],
            text_contrast=row["text_contrast"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create(self, theme: Theme) -> Theme:
        theme_uuid = str(ULID())
        now = _now()
        self.conn.execute(
            text(
                "INSERT INTO themes (uuid, owner_type, owner_id, name, header_font, text_font, "
                "primary_color, primary_light, secondary, secondary_dark, text_color, text_contrast, "
                "created_at, updated_at) "
                "VALUES (:uuid, :owner_type, :owner_id, :name, :header_font, :text_font, "
                ":primary_color, :primary_light, :secondary, :secondary_dark, :text_color, :text_contrast, "
                ":created_at, :updated_at)"
            ),
            {
                "uuid": theme_uuid,
                "owner_type": theme.owner_type,
                "owner_id": theme.owner_id,
                "name": theme.name,
                "header_font": theme.header_font,
                "text_font": theme.text_font,
                "primary_color": theme.primary,
                "primary_light": theme.primary_light,
                "secondary": theme.secondary,
                "secondary_dark": theme.secondary_dark,
                "text_color": theme.text_color,
                "text_contrast": theme.text_contrast,
                "created_at": now,
                "updated_at": now,
            },
        )
        self.conn.commit()
        return self.get_by_owner(theme.owner_type, theme.owner_id)  # type: ignore

    def get_by_id(self, theme_id: int) -> Theme | None:
        row = self.conn.execute(text("SELECT * FROM themes WHERE id = :id"), {"id": theme_id}).mappings().fetchone()
        if row is None:
            return None
        return self._row_to_theme(row)

    def get_by_uuid(self, uuid: str) -> Theme | None:
        row = self.conn.execute(text("SELECT * FROM themes WHERE uuid = :uuid"), {"uuid": uuid}).mappings().fetchone()
        if row is None:
            return None
        return self._row_to_theme(row)

    def get_by_owner(self, owner_type: str, owner_id: int) -> Theme | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM themes WHERE owner_type = :owner_type AND owner_id = :owner_id"),
                {"owner_type": owner_type, "owner_id": owner_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_theme(row)

    def update(self, theme: Theme) -> Theme:
        self.conn.execute(
            text(
                "UPDATE themes SET name = :name, header_font = :header_font, text_font = :text_font, "
                "primary_color = :primary_color, primary_light = :primary_light, secondary = :secondary, "
                "secondary_dark = :secondary_dark, text_color = :text_color, text_contrast = :text_contrast, "
                "updated_at = :updated_at WHERE id = :id"
            ),
            {
                "name": theme.name,
                "header_font": theme.header_font,
                "text_font": theme.text_font,
                "primary_color": theme.primary,
                "primary_light": theme.primary_light,
                "secondary": theme.secondary,
                "secondary_dark": theme.secondary_dark,
                "text_color": theme.text_color,
                "text_contrast": theme.text_contrast,
                "updated_at": _now(),
                "id": theme.id,
            },
        )
        self.conn.commit()
        if theme.id is None:
            raise ValueError("Cannot update theme without an id")
        result = self.get_by_id(theme.id)
        if result is None:
            raise RuntimeError(f"Failed to retrieve theme after update (id={theme.id})")
        return result

    def delete(self, theme_id: int) -> None:
        self.conn.execute(text("DELETE FROM themes WHERE id = :id"), {"id": theme_id})
        self.conn.commit()


class SQLAlchemyPasswordResetTokenRepository(PasswordResetTokenRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row(row: RowMapping) -> PasswordResetToken:
        return PasswordResetToken(
            id=row["id"],
            user_id=row["user_id"],
            token_hash=row["token_hash"],
            expires_at=row["expires_at"],
            used_at=row.get("used_at"),
            created_at=row.get("created_at"),
        )

    def create(self, token: PasswordResetToken) -> PasswordResetToken:
        self.conn.execute(
            text(
                "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at) "
                "VALUES (:user_id, :token_hash, :expires_at, :created_at)"
            ),
            {
                "user_id": token.user_id,
                "token_hash": token.token_hash,
                "expires_at": token.expires_at,
                "created_at": _now(),
            },
        )
        self.conn.commit()
        result = self.get_by_hash(token.token_hash)
        if result is None:
            raise RuntimeError("Failed to retrieve password reset token after create")
        return result

    def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM password_reset_tokens WHERE token_hash = :h"),
                {"h": token_hash},
            )
            .mappings()
            .fetchone()
        )
        return None if row is None else self._row(row)

    def mark_used(self, token_id: int) -> None:
        self.conn.execute(
            text("UPDATE password_reset_tokens SET used_at = :now WHERE id = :id"),
            {"now": _now(), "id": token_id},
        )
        self.conn.commit()

    def invalidate_all_for_user(self, user_id: int) -> None:
        self.conn.execute(
            text("UPDATE password_reset_tokens SET used_at = :now WHERE user_id = :uid AND used_at IS NULL"),
            {"now": _now(), "uid": user_id},
        )
        self.conn.commit()


class SQLAlchemyKnownDeviceRepository(KnownDeviceRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def get(self, user_id: int, device_hash: str) -> KnownDevice | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM known_devices WHERE user_id = :uid AND device_hash = :h"),
                {"uid": user_id, "h": device_hash},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return KnownDevice(
            id=row["id"],
            user_id=row["user_id"],
            device_hash=row["device_hash"],
            user_agent_snippet=row.get("user_agent_snippet", "") or "",
            first_seen_at=row.get("first_seen_at"),
            last_seen_at=row.get("last_seen_at"),
        )

    def upsert(self, device: KnownDevice) -> KnownDevice:
        existing = self.get(device.user_id, device.device_hash)
        now = _now()
        if existing is None:
            self.conn.execute(
                text(
                    "INSERT INTO known_devices (user_id, device_hash, user_agent_snippet, "
                    "first_seen_at, last_seen_at) "
                    "VALUES (:uid, :h, :ua, :now, :now)"
                ),
                {"uid": device.user_id, "h": device.device_hash, "ua": device.user_agent_snippet, "now": now},
            )
        else:
            self.conn.execute(
                text("UPDATE known_devices SET last_seen_at = :now WHERE id = :id"),
                {"now": now, "id": existing.id},
            )
        self.conn.commit()
        result = self.get(device.user_id, device.device_hash)
        if result is None:
            raise RuntimeError("Failed to upsert known_device")
        return result
