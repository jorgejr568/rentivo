from __future__ import annotations

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.encryption.base import EncryptionBackend
from rentivo.models.mfa import RecoveryCode, UserPasskey, UserTOTP
from rentivo.observability import traced
from rentivo.repositories.base import (
    MFATOTPRepository,
    PasskeyRepository,
    RecoveryCodeRepository,
)
from rentivo.repositories.sqlalchemy._common import _now


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

    @traced("totp_repo.get_by_user_id")
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

    @traced("totp_repo.create")
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

    @traced("totp_repo.confirm")
    def confirm(self, user_id: int) -> None:
        self.conn.execute(
            text("UPDATE user_totp SET confirmed = 1, confirmed_at = :now WHERE user_id = :user_id"),
            {"now": _now(), "user_id": user_id},
        )
        self.conn.commit()

    @traced("totp_repo.delete_by_user_id")
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

    @traced("recovery_code_repo.create_batch")
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

    @traced("recovery_code_repo.list_unused_by_user")
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

    @traced("recovery_code_repo.mark_used")
    def mark_used(self, code_id: int) -> None:
        self.conn.execute(
            text("UPDATE user_recovery_codes SET used_at = :now WHERE id = :id"),
            {"now": _now(), "id": code_id},
        )
        self.conn.commit()

    @traced("recovery_code_repo.delete_all_by_user")
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

    @traced("passkey_repo.create")
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

    @traced("passkey_repo.get_by_uuid")
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

    @traced("passkey_repo.get_by_credential_id")
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

    @traced("passkey_repo.list_by_user")
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

    @traced("passkey_repo.update_sign_count")
    def update_sign_count(self, passkey_id: int, sign_count: int) -> None:
        self.conn.execute(
            text("UPDATE user_passkeys SET sign_count = :sign_count WHERE id = :id"),
            {"sign_count": sign_count, "id": passkey_id},
        )
        self.conn.commit()

    @traced("passkey_repo.update_last_used")
    def update_last_used(self, passkey_id: int) -> None:
        self.conn.execute(
            text("UPDATE user_passkeys SET last_used_at = :now WHERE id = :id"),
            {"now": _now(), "id": passkey_id},
        )
        self.conn.commit()

    @traced("passkey_repo.delete")
    def delete(self, passkey_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM user_passkeys WHERE id = :id"),
            {"id": passkey_id},
        )
        self.conn.commit()
