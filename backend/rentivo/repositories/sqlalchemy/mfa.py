from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import Connection, bindparam, column, select, table, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.encryption.base import EncryptionBackend
from rentivo.models.mfa import MFAFactorRemovalResult, RecoveryCode, UserPasskey, UserTOTP
from rentivo.observability import traced
from rentivo.repositories.base import (
    MFAFactorRepository,
    MFATOTPRepository,
    PasskeyRepository,
    RecoveryCodeRepository,
)
from rentivo.repositories.sqlalchemy._common import _now

_USERS = table("users", column("id"))
_ORGANIZATIONS = table("organizations", column("id"), column("enforce_mfa"), column("deleted_at"))
_ORGANIZATION_MEMBERS = table("organization_members", column("organization_id"), column("user_id"))
_USER_TOTP = table("user_totp", column("user_id"), column("confirmed"))
_USER_PASSKEYS = table("user_passkeys", column("id"), column("uuid"), column("user_id"))
_USER_ID = bindparam("user_id")

_USER_LOCK = select(_USERS.c.id).where(_USERS.c.id == _USER_ID).with_for_update()
_ENFORCING_ORG_LOCK = (
    select(_ORGANIZATIONS.c.id)
    .select_from(
        _ORGANIZATIONS.join(
            _ORGANIZATION_MEMBERS,
            _ORGANIZATIONS.c.id == _ORGANIZATION_MEMBERS.c.organization_id,
        )
    )
    .where(
        _ORGANIZATION_MEMBERS.c.user_id == _USER_ID,
        _ORGANIZATIONS.c.enforce_mfa == 1,
        _ORGANIZATIONS.c.deleted_at.is_(None),
    )
    .limit(1)
    .with_for_update()
)
_TOTP_FACTOR_LOCK = select(_USER_TOTP.c.confirmed).where(_USER_TOTP.c.user_id == _USER_ID).with_for_update()
_PASSKEY_FACTORS_LOCK = (
    select(_USER_PASSKEYS.c.id, _USER_PASSKEYS.c.uuid).where(_USER_PASSKEYS.c.user_id == _USER_ID).with_for_update()
)


def _next_usage_time(expected: datetime | None) -> datetime:
    current = _now()
    if expected is None:
        return current
    if expected.tzinfo is None and current.tzinfo is not None:
        current = current.replace(tzinfo=None)
    elif expected.tzinfo is not None and current.tzinfo is None:
        current = current.replace(tzinfo=expected.tzinfo)
    return max(current, expected + timedelta(microseconds=1))


class SQLAlchemyMFAFactorRepository(MFAFactorRepository):
    """Serializes factor removal and session revocation on the owning user row."""

    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def _lock_user(self, user_id: int) -> bool:
        return self.conn.execute(_USER_LOCK, {"user_id": user_id}).fetchone() is not None

    def _user_has_enforcing_org(self, user_id: int) -> bool:
        return self.conn.execute(_ENFORCING_ORG_LOCK, {"user_id": user_id}).fetchone() is not None

    def _revoke_login_tokens(self, user_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM api_keys WHERE user_id = :user_id AND is_login_token = 1"),
            {"user_id": user_id},
        )

    @traced("mfa_factor_repo.remove_totp_and_revoke_logins")
    def remove_totp_and_revoke_logins(self, user_id: int) -> MFAFactorRemovalResult:
        # Authentication performs reads on this request connection first. End
        # that read view before locking so MariaDB always starts current.
        self.conn.rollback()
        try:
            if not self._lock_user(user_id):
                self.conn.rollback()
                return MFAFactorRemovalResult.NOT_FOUND
            totp = self.conn.execute(_TOTP_FACTOR_LOCK, {"user_id": user_id}).fetchone()
            if totp is None:
                self.conn.rollback()
                return MFAFactorRemovalResult.NOT_FOUND
            passkeys = self.conn.execute(_PASSKEY_FACTORS_LOCK, {"user_id": user_id}).fetchall()
            if bool(totp[0]) and not passkeys and self._user_has_enforcing_org(user_id):
                self.conn.rollback()
                return MFAFactorRemovalResult.LAST_FACTOR
            self.conn.execute(
                text("DELETE FROM user_totp WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            self.conn.execute(
                text("DELETE FROM user_recovery_codes WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            self._revoke_login_tokens(user_id)
            self.conn.commit()
            return MFAFactorRemovalResult.REMOVED
        except BaseException:
            self.conn.rollback()
            raise

    @traced("mfa_factor_repo.remove_passkey_and_revoke_logins")
    def remove_passkey_and_revoke_logins(
        self,
        passkey_uuid: str,
        user_id: int,
    ) -> MFAFactorRemovalResult:
        self.conn.rollback()
        try:
            if not self._lock_user(user_id):
                self.conn.rollback()
                return MFAFactorRemovalResult.NOT_FOUND
            totp = self.conn.execute(_TOTP_FACTOR_LOCK, {"user_id": user_id}).fetchone()
            passkeys = self.conn.execute(_PASSKEY_FACTORS_LOCK, {"user_id": user_id}).mappings().all()
            passkey = next((candidate for candidate in passkeys if candidate["uuid"] == passkey_uuid), None)
            if passkey is None:
                self.conn.rollback()
                return MFAFactorRemovalResult.NOT_FOUND
            has_confirmed_totp = totp is not None and bool(totp[0])
            if not has_confirmed_totp and len(passkeys) == 1 and self._user_has_enforcing_org(user_id):
                self.conn.rollback()
                return MFAFactorRemovalResult.LAST_FACTOR
            self.conn.execute(
                text("DELETE FROM user_passkeys WHERE id = :passkey_id"),
                {"passkey_id": passkey["id"]},
            )
            self._revoke_login_tokens(user_id)
            self.conn.commit()
            return MFAFactorRemovalResult.REMOVED
        except BaseException:
            self.conn.rollback()
            raise


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
    def mark_used(self, code_id: int) -> bool:
        result = self.conn.execute(
            text("UPDATE user_recovery_codes SET used_at = :now WHERE id = :id AND used_at IS NULL"),
            {"now": _now(), "id": code_id},
        )
        self.conn.commit()
        return result.rowcount > 0

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
    def update_sign_count(
        self,
        passkey_id: int,
        expected_sign_count: int,
        expected_last_used_at: datetime | None,
        new_sign_count: int,
    ) -> bool:
        result = self.conn.execute(
            text(
                "UPDATE user_passkeys SET sign_count = :new_sign_count, last_used_at = :now "
                "WHERE id = :id AND sign_count = :expected_sign_count "
                "AND ((last_used_at IS NULL AND :expected_last_used_at IS NULL) "
                "OR last_used_at = :expected_last_used_at)"
            ),
            {
                "new_sign_count": new_sign_count,
                "now": _next_usage_time(expected_last_used_at),
                "id": passkey_id,
                "expected_sign_count": expected_sign_count,
                "expected_last_used_at": expected_last_used_at,
            },
        )
        self.conn.commit()
        return result.rowcount > 0

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
