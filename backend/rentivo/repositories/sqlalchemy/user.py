from __future__ import annotations

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError

from rentivo.encryption.base import EncryptionBackend
from rentivo.models.user import User
from rentivo.observability import traced
from rentivo.repositories.base import UserAlreadyRegisteredError, UserRepository
from rentivo.repositories.sqlalchemy._common import _now


class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, conn: Connection, encryption: EncryptionBackend) -> None:
        self.conn = conn
        self.encryption = encryption

    def _row_to_user(self, row: RowMapping) -> User:
        return User(
            id=row["id"],
            email=self.encryption.decrypt(row["email"] or ""),
            password_hash=row["password_hash"],
            pix_key=self.encryption.decrypt(row.get("pix_key", "") or ""),
            pix_merchant_name=self.encryption.decrypt(row.get("pix_merchant_name", "") or ""),
            pix_merchant_city=self.encryption.decrypt(row.get("pix_merchant_city", "") or ""),
            created_at=row["created_at"],
        )

    @traced("user_repo.create")
    def create(self, user: User) -> User:
        from rentivo.blind_index import compute_email_hash

        try:
            self.conn.execute(
                text(
                    "INSERT INTO users (email, email_hash, password_hash, created_at) "
                    "VALUES (:email, :email_hash, :password_hash, :created_at)"
                ),
                {
                    "email": self.encryption.encrypt(user.email),
                    "email_hash": compute_email_hash(user.email),
                    "password_hash": user.password_hash,
                    "created_at": _now(),
                },
            )
            self.conn.commit()
        except IntegrityError:
            self.conn.rollback()
            raise UserAlreadyRegisteredError(f"Email '{user.email}' is already registered") from None
        result = self.get_by_email(user.email)
        if result is None:
            raise RuntimeError("Failed to retrieve user after create")
        return result

    @traced("user_repo.get_by_id")
    def get_by_id(self, user_id: int) -> User | None:
        row = self.conn.execute(text("SELECT * FROM users WHERE id = :id"), {"id": user_id}).mappings().fetchone()
        return None if row is None else self._row_to_user(row)

    @traced("user_repo.get_by_email")
    def get_by_email(self, email: str) -> User | None:
        """Look up by deterministic blind index. Falls back to plaintext for legacy rows."""
        from rentivo.blind_index import compute_email_hash

        email_hash = compute_email_hash(email)
        row = (
            self.conn.execute(
                text("SELECT * FROM users WHERE email_hash = :hash"),
                {"hash": email_hash},
            )
            .mappings()
            .fetchone()
        )
        if row is not None:
            return self._row_to_user(row)

        # Legacy fallback: a row written before the migration ran has its
        # plaintext email and NULL hash. The migration LOWER+TRIM'd every
        # legacy row, so the fallback compares the normalized input against
        # the (already-normalized) stored value.
        # TODO: remove this fallback once `make backfill-encryption` has been
        # run in production and every row has a non-NULL email_hash.
        row = (
            self.conn.execute(
                text("SELECT * FROM users WHERE email_hash IS NULL AND email = :normalized"),
                {"normalized": email.strip().lower()},
            )
            .mappings()
            .fetchone()
        )
        return None if row is None else self._row_to_user(row)

    @traced("user_repo.list_all")
    def list_all(self) -> list[User]:
        rows = self.conn.execute(text("SELECT * FROM users ORDER BY created_at DESC")).mappings().fetchall()
        return [self._row_to_user(row) for row in rows]

    @traced("user_repo.update_password_hash")
    def update_password_hash(self, user_id: int, password_hash: str) -> None:
        self.conn.execute(
            text("UPDATE users SET password_hash = :password_hash WHERE id = :id"),
            {"password_hash": password_hash, "id": user_id},
        )
        self.conn.commit()

    @traced("user_repo.change_password_and_revoke_other_login_tokens")
    def change_password_and_revoke_other_login_tokens(
        self,
        user_id: int,
        password_hash: str,
        current_key_uuid: str,
    ) -> int:
        try:
            self.conn.execute(
                text("UPDATE users SET password_hash = :password_hash WHERE id = :id"),
                {"password_hash": password_hash, "id": user_id},
            )
            result = self.conn.execute(
                text(
                    "DELETE FROM api_keys WHERE user_id = :user_id AND is_login_token = 1 AND uuid != :current_key_uuid"
                ),
                {"user_id": user_id, "current_key_uuid": current_key_uuid},
            )
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise
        return result.rowcount

    @traced("user_repo.delete")
    def delete(self, user_id: int) -> bool:
        result = self.conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        self.conn.commit()
        return result.rowcount > 0

    @traced("user_repo.update_pix")
    def update_pix(self, user_id: int, pix_key: str, pix_merchant_name: str, pix_merchant_city: str) -> None:
        self.conn.execute(
            text(
                "UPDATE users SET pix_key = :pix_key, pix_merchant_name = :pix_merchant_name, "
                "pix_merchant_city = :pix_merchant_city WHERE id = :id"
            ),
            {
                "pix_key": self.encryption.encrypt(pix_key),
                "pix_merchant_name": self.encryption.encrypt(pix_merchant_name),
                "pix_merchant_city": self.encryption.encrypt(pix_merchant_city),
                "id": user_id,
            },
        )
        self.conn.commit()
