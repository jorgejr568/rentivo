from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.constants import SP_TZ
from rentivo.encryption.base import EncryptionBackend
from rentivo.models.known_device import KnownDevice
from rentivo.models.mfa import RecoveryCode, UserPasskey, UserTOTP
from rentivo.models.password_reset_token import PasswordResetToken
from rentivo.models.theme import Theme
from rentivo.repositories.base import (
    KnownDeviceRepository,
    MFATOTPRepository,
    PasskeyRepository,
    PasswordResetTokenRepository,
    RecoveryCodeRepository,
    ThemeRepository,
)


def _now() -> datetime:
    return datetime.now(SP_TZ)


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
