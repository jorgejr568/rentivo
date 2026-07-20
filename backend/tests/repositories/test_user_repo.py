from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from rentivo.models.user import User
from rentivo.repositories.base import UserAlreadyRegisteredError
from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository


def _insert_api_key(db_connection, *, user_id: int, uuid: str, is_login_token: bool) -> None:
    db_connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS api_keys ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, uuid VARCHAR(64) NOT NULL UNIQUE, "
            "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, name VARCHAR(255) NOT NULL, "
            "secret_hash BLOB NOT NULL UNIQUE, key_start VARCHAR(4) NOT NULL, key_end VARCHAR(2) NOT NULL, "
            "is_login_token BOOLEAN NOT NULL DEFAULT 0, expires_at DATETIME NOT NULL, "
            "last_used_at DATETIME NULL, created_at DATETIME NOT NULL, revoked_at DATETIME NULL)"
        )
    )
    db_connection.execute(
        text(
            "INSERT INTO api_keys "
            "(uuid, user_id, name, secret_hash, key_start, key_end, is_login_token, expires_at, created_at) "
            "VALUES (:uuid, :user_id, :name, :secret_hash, 'abcd', 'yz', :is_login_token, "
            "'2099-01-01 00:00:00', '2026-07-17 12:00:00')"
        ),
        {
            "uuid": uuid,
            "user_id": user_id,
            "name": uuid,
            "secret_hash": uuid.encode().ljust(32, b"0")[:32],
            "is_login_token": is_login_token,
        },
    )
    db_connection.commit()


class TestUserRepo:
    def test_create_and_get(self, user_repo: SQLAlchemyUserRepository):
        user = User(email="admin@example.com", password_hash="hash123")
        created = user_repo.create(user)

        assert created.id is not None
        assert created.email == "admin@example.com"
        assert created.password_hash == "hash123"

    def test_get_by_email_returns_user(self, user_repo: SQLAlchemyUserRepository):
        user_repo.create(User(email="alice@example.com", password_hash="x"))
        found = user_repo.get_by_email("alice@example.com")

        assert found is not None
        assert found.email == "alice@example.com"

    def test_get_by_email_returns_none_for_unknown(self, user_repo: SQLAlchemyUserRepository):
        assert user_repo.get_by_email("nobody@example.com") is None

    def test_list_all(self, user_repo: SQLAlchemyUserRepository):
        user_repo.create(User(email="admin1@example.com", password_hash="hash1"))
        user_repo.create(User(email="admin2@example.com", password_hash="hash2"))

        users = user_repo.list_all()
        assert len(users) == 2

    def test_list_all_empty(self, user_repo: SQLAlchemyUserRepository):
        assert user_repo.list_all() == []

    def test_update_password_hash_by_user_id(self, user_repo: SQLAlchemyUserRepository):
        user = user_repo.create(User(email="alice@example.com", password_hash="old"))
        user_repo.update_password_hash(user.id, "new-hash")

        refreshed = user_repo.get_by_id(user.id)
        assert refreshed is not None
        assert refreshed.password_hash == "new-hash"

    def test_change_password_and_revoke_other_logins_is_one_transaction(
        self,
        user_repo: SQLAlchemyUserRepository,
        db_connection,
    ):
        user = user_repo.create(User(email="atomic@example.com", password_hash="old-hash"))
        _insert_api_key(db_connection, user_id=user.id, uuid="current-login", is_login_token=True)
        _insert_api_key(db_connection, user_id=user.id, uuid="other-login", is_login_token=True)
        _insert_api_key(db_connection, user_id=user.id, uuid="integration", is_login_token=False)

        revoked = user_repo.change_password_and_revoke_other_login_tokens(
            user.id,
            "new-hash",
            "current-login",
        )

        refreshed = user_repo.get_by_id(user.id)
        remaining = (
            db_connection.execute(
                text("SELECT uuid FROM api_keys WHERE user_id = :user_id ORDER BY uuid"),
                {"user_id": user.id},
            )
            .scalars()
            .all()
        )
        assert refreshed is not None
        assert refreshed.password_hash == "new-hash"
        assert revoked == 1
        assert remaining == ["current-login", "integration"]

    def test_change_password_rolls_back_hash_when_login_revocation_fails(
        self,
        user_repo: SQLAlchemyUserRepository,
        db_connection,
    ):
        user = user_repo.create(User(email="rollback@example.com", password_hash="old-hash"))
        _insert_api_key(db_connection, user_id=user.id, uuid="current-login", is_login_token=True)
        _insert_api_key(db_connection, user_id=user.id, uuid="other-login", is_login_token=True)
        db_connection.execute(
            text(
                "CREATE TRIGGER fail_login_revoke BEFORE DELETE ON api_keys "
                "WHEN OLD.uuid = 'other-login' BEGIN SELECT RAISE(ABORT, 'forced failure'); END"
            )
        )
        db_connection.commit()

        with pytest.raises(SQLAlchemyError):
            user_repo.change_password_and_revoke_other_login_tokens(
                user.id,
                "must-roll-back",
                "current-login",
            )

        refreshed = user_repo.get_by_id(user.id)
        remaining = (
            db_connection.execute(
                text("SELECT uuid FROM api_keys WHERE user_id = :user_id ORDER BY uuid"),
                {"user_id": user.id},
            )
            .scalars()
            .all()
        )
        assert refreshed is not None
        assert refreshed.password_hash == "old-hash"
        assert remaining == ["current-login", "other-login"]

    def test_get_by_id(self, user_repo: SQLAlchemyUserRepository):
        created = user_repo.create(User(email="admin@example.com", password_hash="hash"))
        fetched = user_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.email == "admin@example.com"

    def test_get_by_id_not_found(self, user_repo: SQLAlchemyUserRepository):
        assert user_repo.get_by_id(9999) is None

    def test_create_runtime_error(self, user_repo: SQLAlchemyUserRepository):
        with patch.object(user_repo, "get_by_email", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve user after create"):
                user_repo.create(User(email="admin@example.com", password_hash="hash"))

    def test_create_maps_concurrent_duplicate_to_domain_error(self, user_repo: SQLAlchemyUserRepository):
        user_repo.create(User(email="duplicate@example.com", password_hash="hash"))

        with pytest.raises(UserAlreadyRegisteredError):
            user_repo.create(User(email="duplicate@example.com", password_hash="hash"))

    def test_delete_is_idempotent(self, user_repo: SQLAlchemyUserRepository):
        user = user_repo.create(User(email="delete-me@example.com", password_hash="hash"))

        assert user.id is not None
        assert user_repo.delete(user.id) is True
        assert user_repo.delete(user.id) is False
        assert user_repo.get_by_id(user.id) is None


class TestUserRepoEncryption:
    def test_update_pix_encrypts_in_db(self, db_connection, fake_encryption):
        from sqlalchemy import text

        from rentivo.models.user import User
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

        repo = SQLAlchemyUserRepository(db_connection, fake_encryption)
        user = repo.create(User(email="alice@example.com", password_hash="x"))
        repo.update_pix(user.id, "alice@pix.com", "Alice", "Sao Paulo")

        row = (
            db_connection.execute(
                text("SELECT pix_key, pix_merchant_name, pix_merchant_city FROM users WHERE id = :id"),
                {"id": user.id},
            )
            .mappings()
            .fetchone()
        )
        assert row["pix_key"] == "fake:alice@pix.com"
        assert row["pix_merchant_name"] == "fake:Alice"
        assert row["pix_merchant_city"] == "fake:Sao Paulo"

    def test_get_by_id_decrypts_pix(self, db_connection, fake_encryption):
        from rentivo.models.user import User
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

        repo = SQLAlchemyUserRepository(db_connection, fake_encryption)
        user = repo.create(User(email="alice@example.com", password_hash="x"))
        repo.update_pix(user.id, "alice@pix.com", "Alice", "Sao Paulo")

        fetched = repo.get_by_id(user.id)
        assert fetched is not None
        assert fetched.pix_key == "alice@pix.com"
        assert fetched.pix_merchant_name == "Alice"
        assert fetched.pix_merchant_city == "Sao Paulo"

    def test_get_handles_legacy_plaintext(self, db_connection, fake_encryption):
        from sqlalchemy import text

        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

        db_connection.execute(
            text(
                "INSERT INTO users (email, password_hash, pix_key, pix_merchant_name, "
                "pix_merchant_city) VALUES (:email, :ph, :pk, :pmn, :pmc)"
            ),
            {
                "email": "legacy@example.com",
                "ph": "x",
                "pk": "legacy@pix.com",
                "pmn": "Legacy",
                "pmc": "Legacy City",
            },
        )
        db_connection.commit()

        repo = SQLAlchemyUserRepository(db_connection, fake_encryption)
        fetched = repo.get_by_email("legacy@example.com")
        assert fetched is not None
        assert fetched.pix_key == "legacy@pix.com"
        assert fetched.pix_merchant_name == "Legacy"
        assert fetched.pix_merchant_city == "Legacy City"
        assert fetched.email == "legacy@example.com"


class TestUserRepoEmailEncryption:
    """Email is encrypted at rest and looked up by HMAC blind index."""

    def test_create_stores_ciphertext_in_email_column(self, db_connection, fake_encryption, monkeypatch):
        from sqlalchemy import text

        import rentivo.blind_index
        from rentivo.models.user import User
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

        # Stub the blind-index key so the hash is deterministic for assertions.
        monkeypatch.setattr(rentivo.blind_index, "_cached_key", b"\x01" * 32)

        repo = SQLAlchemyUserRepository(db_connection, fake_encryption)
        created = repo.create(User(email="Alice@Example.com", password_hash="x"))

        row = (
            db_connection.execute(
                text("SELECT email, email_hash FROM users WHERE id = :id"),
                {"id": created.id},
            )
            .mappings()
            .fetchone()
        )
        assert row["email"] == "fake:Alice@Example.com"
        # Hash is hex SHA256 over lower-cased+stripped email under the stub key.
        from rentivo.blind_index import compute_email_hash

        assert row["email_hash"] == compute_email_hash("Alice@Example.com")
        # The Pydantic model surfaces decrypted plaintext to callers.
        assert created.email == "Alice@Example.com"

    def test_get_by_email_uses_blind_index(self, db_connection, fake_encryption, monkeypatch):
        import rentivo.blind_index
        from rentivo.models.user import User
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

        monkeypatch.setattr(rentivo.blind_index, "_cached_key", b"\x02" * 32)

        repo = SQLAlchemyUserRepository(db_connection, fake_encryption)
        repo.create(User(email="bob@example.com", password_hash="x"))

        # Case + whitespace variations match the same row.
        for variant in ("bob@example.com", "Bob@Example.COM", "  bob@example.com  "):
            found = repo.get_by_email(variant)
            assert found is not None
            assert found.email == "bob@example.com"

    def test_get_by_email_returns_none_for_unknown(self, db_connection, fake_encryption, monkeypatch):
        import rentivo.blind_index
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

        monkeypatch.setattr(rentivo.blind_index, "_cached_key", b"\x03" * 32)

        repo = SQLAlchemyUserRepository(db_connection, fake_encryption)
        assert repo.get_by_email("nobody@example.com") is None

    def test_list_all_decrypts_email(self, db_connection, fake_encryption, monkeypatch):
        import rentivo.blind_index
        from rentivo.models.user import User
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

        monkeypatch.setattr(rentivo.blind_index, "_cached_key", b"\x04" * 32)

        repo = SQLAlchemyUserRepository(db_connection, fake_encryption)
        repo.create(User(email="a@example.com", password_hash="x"))
        repo.create(User(email="b@example.com", password_hash="x"))

        emails = sorted(u.email for u in repo.list_all())
        assert emails == ["a@example.com", "b@example.com"]

    def test_get_by_email_handles_legacy_plaintext_row(self, db_connection, fake_encryption, monkeypatch):
        """A row written before the migration ran has plaintext email and NULL hash.

        Until the backfill runs, ``get_by_email`` must still find it. The
        migration LOWER+TRIM'd every legacy row, so the fallback compares
        the normalized input against the (already-normalized) stored value.
        """
        from sqlalchemy import text

        import rentivo.blind_index
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

        monkeypatch.setattr(rentivo.blind_index, "_cached_key", b"\x05" * 32)

        # Simulate a post-migration legacy row: already lowercased and trimmed.
        db_connection.execute(
            text(
                "INSERT INTO users (email, email_hash, password_hash, created_at) "
                "VALUES ('legacy@example.com', NULL, 'x', '2026-04-01 00:00:00')"
            )
        )
        db_connection.commit()

        repo = SQLAlchemyUserRepository(db_connection, fake_encryption)
        # Case + whitespace variations all reach the normalized stored row.
        for variant in ("legacy@example.com", "Legacy@Example.com", "  legacy@example.com  "):
            found = repo.get_by_email(variant)
            assert found is not None, f"variant {variant!r} did not match the legacy row"
            assert found.email == "legacy@example.com"
