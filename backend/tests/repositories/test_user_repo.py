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


def _seed_account_graph(db_connection) -> None:
    """Arrange user 1 with auth artifacts, owned content, a solo org, and a shared org.

    User 1 is the account under test; user 2 shares the second organization so the
    solo/shared branch of the org soft-delete is exercised. All rows are inserted
    raw so SQLite's foreign keys (``PRAGMA foreign_keys = ON``) drive real cascades.
    """
    now = "2026-07-01 12:00:00"
    for uid, ehash in ((1, "hash-1"), (2, "hash-2")):
        db_connection.execute(
            text(
                "INSERT INTO users (id, email, email_hash, password_hash, created_at) "
                "VALUES (:id, :email, :hash, 'x', :now)"
            ),
            {"id": uid, "email": f"u{uid}@example.com", "hash": ehash, "now": now},
        )
    # Auth artifact that cascades away with the user row.
    db_connection.execute(
        text(
            "INSERT INTO user_passkeys (uuid, user_id, credential_id, public_key, created_at) "
            "VALUES ('pk-1', 1, 'cred', 'pub', :now)"
        ),
        {"now": now},
    )
    # User-owned billing (soft-deleted, not cascaded) and a peer billing that must survive.
    db_connection.execute(
        text(
            "INSERT INTO billings (name, uuid, owner_type, owner_id, created_at, updated_at) "
            "VALUES ('Mine', 'b-user-1', 'user', 1, :now, :now), "
            "('Theirs', 'b-user-2', 'user', 2, :now, :now)"
        ),
        {"now": now},
    )
    # Solo org: user 1 is the only member -> soft-deleted.
    db_connection.execute(
        text(
            "INSERT INTO organizations (id, uuid, name, created_by, created_at, updated_at) "
            "VALUES (10, 'org-solo', 'Solo', 1, :now, :now)"
        ),
        {"now": now},
    )
    db_connection.execute(
        text(
            "INSERT INTO organization_members (organization_id, user_id, role, created_at) "
            "VALUES (10, 1, 'admin', :now)"
        ),
        {"now": now},
    )
    # Shared org: users 1 and 2 are both members -> survives with created_by nulled.
    db_connection.execute(
        text(
            "INSERT INTO organizations (id, uuid, name, created_by, created_at, updated_at) "
            "VALUES (20, 'org-shared', 'Shared', 1, :now, :now)"
        ),
        {"now": now},
    )
    db_connection.execute(
        text(
            "INSERT INTO organization_members (organization_id, user_id, role, created_at) "
            "VALUES (20, 1, 'admin', :now), (20, 2, 'admin', :now)"
        ),
        {"now": now},
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

    def test_delete_account_soft_deletes_content_and_hard_deletes_user(self, db_connection, fake_encryption):
        repo = SQLAlchemyUserRepository(db_connection, fake_encryption)
        _seed_account_graph(db_connection)
        _insert_api_key(db_connection, user_id=1, uuid="login-1", is_login_token=True)

        assert repo.delete_account(1) is True

        # User and its cascading auth artifacts are gone.
        assert db_connection.execute(text("SELECT COUNT(*) FROM users WHERE id = 1")).scalar() == 0
        assert db_connection.execute(text("SELECT COUNT(*) FROM user_passkeys WHERE user_id = 1")).scalar() == 0
        assert db_connection.execute(text("SELECT COUNT(*) FROM api_keys WHERE user_id = 1")).scalar() == 0
        assert db_connection.execute(text("SELECT COUNT(*) FROM organization_members WHERE user_id = 1")).scalar() == 0
        # User-owned billing soft-deleted; the peer user's billing is untouched.
        assert (
            db_connection.execute(
                text("SELECT deleted_at FROM billings WHERE owner_type = 'user' AND owner_id = 1")
            ).scalar()
            is not None
        )
        assert (
            db_connection.execute(
                text("SELECT deleted_at FROM billings WHERE owner_type = 'user' AND owner_id = 2")
            ).scalar()
            is None
        )
        # Solo org soft-deleted; shared org survives with created_by nulled and not soft-deleted.
        assert db_connection.execute(text("SELECT deleted_at FROM organizations WHERE id = 10")).scalar() is not None
        row = db_connection.execute(text("SELECT deleted_at, created_by FROM organizations WHERE id = 20")).fetchone()
        assert row[0] is None and row[1] is None
        # The peer user is unaffected.
        assert db_connection.execute(text("SELECT COUNT(*) FROM users WHERE id = 2")).scalar() == 1

    def test_delete_account_returns_false_for_missing_user(self, db_connection, fake_encryption):
        repo = SQLAlchemyUserRepository(db_connection, fake_encryption)
        assert repo.delete_account(999) is False

    def test_delete_account_rolls_back_when_user_delete_fails(self, db_connection, fake_encryption):
        repo = SQLAlchemyUserRepository(db_connection, fake_encryption)
        _seed_account_graph(db_connection)
        # Force the final hard-delete to abort after the soft-delete UPDATEs have run.
        db_connection.execute(
            text(
                "CREATE TRIGGER fail_user_delete BEFORE DELETE ON users "
                "WHEN OLD.id = 1 BEGIN SELECT RAISE(ABORT, 'forced failure'); END"
            )
        )
        db_connection.commit()

        with pytest.raises(SQLAlchemyError):
            repo.delete_account(1)

        # All-or-nothing: the user survives and no soft-delete stuck.
        assert db_connection.execute(text("SELECT COUNT(*) FROM users WHERE id = 1")).scalar() == 1
        assert (
            db_connection.execute(
                text("SELECT deleted_at FROM billings WHERE owner_type = 'user' AND owner_id = 1")
            ).scalar()
            is None
        )
        assert db_connection.execute(text("SELECT deleted_at FROM organizations WHERE id = 10")).scalar() is None


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
