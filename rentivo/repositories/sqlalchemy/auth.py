from __future__ import annotations

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping

from rentivo.models.known_device import KnownDevice
from rentivo.models.password_reset_token import PasswordResetToken
from rentivo.repositories.base import (
    KnownDeviceRepository,
    PasswordResetTokenRepository,
)
from rentivo.repositories.sqlalchemy._common import _now


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
