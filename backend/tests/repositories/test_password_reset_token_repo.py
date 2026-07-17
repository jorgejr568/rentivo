from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import text

from rentivo.models.password_reset_token import PasswordResetToken
from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyPasswordResetTokenRepository,
    SQLAlchemyUserRepository,
)


class TestPasswordResetTokenRepo:
    @staticmethod
    def _create_api_keys_table(password_reset_token_repo: SQLAlchemyPasswordResetTokenRepository) -> None:
        password_reset_token_repo.conn.execute(
            text(
                "CREATE TABLE api_keys ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "is_login_token TINYINT NOT NULL DEFAULT 0)"
            )
        )
        password_reset_token_repo.conn.commit()

    def _make_user(
        self,
        user_repo: SQLAlchemyUserRepository,
        email: str = "a@b.com",
    ) -> User:
        return user_repo.create(User(email=email, password_hash="x"))

    def test_create_and_get_by_hash(
        self,
        user_repo: SQLAlchemyUserRepository,
        password_reset_token_repo: SQLAlchemyPasswordResetTokenRepository,
    ):
        user = self._make_user(user_repo)
        token = PasswordResetToken(
            user_id=user.id,
            token_hash="abc-hash",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        created = password_reset_token_repo.create(token)
        assert created.id is not None
        assert created.user_id == user.id
        assert created.used_at is None

        found = password_reset_token_repo.get_by_hash("abc-hash")
        assert found is not None
        assert found.user_id == user.id
        assert found.used_at is None

    def test_get_by_hash_returns_none_for_unknown(
        self,
        password_reset_token_repo: SQLAlchemyPasswordResetTokenRepository,
    ):
        assert password_reset_token_repo.get_by_hash("nope") is None

    def test_mark_used(
        self,
        user_repo: SQLAlchemyUserRepository,
        password_reset_token_repo: SQLAlchemyPasswordResetTokenRepository,
    ):
        user = self._make_user(user_repo, email="b@b.com")
        password_reset_token_repo.create(
            PasswordResetToken(
                user_id=user.id,
                token_hash="h",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        created = password_reset_token_repo.get_by_hash("h")
        assert created is not None
        password_reset_token_repo.mark_used(created.id)
        refreshed = password_reset_token_repo.get_by_hash("h")
        assert refreshed is not None
        assert refreshed.used_at is not None

    def test_invalidate_all_for_user(
        self,
        user_repo: SQLAlchemyUserRepository,
        password_reset_token_repo: SQLAlchemyPasswordResetTokenRepository,
    ):
        user = self._make_user(user_repo, email="c@b.com")
        expires = datetime.now(UTC) + timedelta(hours=1)
        password_reset_token_repo.create(PasswordResetToken(user_id=user.id, token_hash="a", expires_at=expires))
        password_reset_token_repo.create(PasswordResetToken(user_id=user.id, token_hash="b", expires_at=expires))

        password_reset_token_repo.invalidate_all_for_user(user.id)

        a = password_reset_token_repo.get_by_hash("a")
        b = password_reset_token_repo.get_by_hash("b")
        assert a is not None and a.used_at is not None
        assert b is not None and b.used_at is not None

    def test_invalidate_all_for_user_skips_already_used(
        self,
        user_repo: SQLAlchemyUserRepository,
        password_reset_token_repo: SQLAlchemyPasswordResetTokenRepository,
    ):
        user = self._make_user(user_repo, email="d@b.com")
        expires = datetime.now(UTC) + timedelta(hours=1)
        password_reset_token_repo.create(PasswordResetToken(user_id=user.id, token_hash="x", expires_at=expires))
        created = password_reset_token_repo.get_by_hash("x")
        assert created is not None

        password_reset_token_repo.mark_used(created.id)
        first_used_at = password_reset_token_repo.get_by_hash("x").used_at

        password_reset_token_repo.invalidate_all_for_user(user.id)
        second_used_at = password_reset_token_repo.get_by_hash("x").used_at

        # The used_at value should not be overwritten by the bulk invalidation.
        assert first_used_at == second_used_at

    def test_create_runtime_error(
        self,
        user_repo: SQLAlchemyUserRepository,
        password_reset_token_repo: SQLAlchemyPasswordResetTokenRepository,
    ):
        user = self._make_user(user_repo, email="e@b.com")
        with patch.object(password_reset_token_repo, "get_by_hash", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve password reset token after create"):
                password_reset_token_repo.create(
                    PasswordResetToken(
                        user_id=user.id,
                        token_hash="zzz",
                        expires_at=datetime.now(UTC) + timedelta(hours=1),
                    )
                )

    def test_complete_password_reset_is_single_use_and_atomic(
        self,
        user_repo: SQLAlchemyUserRepository,
        password_reset_token_repo: SQLAlchemyPasswordResetTokenRepository,
    ):
        self._create_api_keys_table(password_reset_token_repo)
        user = self._make_user(user_repo, email="atomic@b.com")
        now = datetime.now(UTC)
        first = password_reset_token_repo.create(
            PasswordResetToken(user_id=user.id, token_hash="atomic-a", expires_at=now + timedelta(hours=1))
        )
        password_reset_token_repo.create(
            PasswordResetToken(user_id=user.id, token_hash="atomic-b", expires_at=now + timedelta(hours=1))
        )
        password_reset_token_repo.conn.execute(
            text("INSERT INTO api_keys (user_id, is_login_token) VALUES (:uid, 1), (:uid, 0)"),
            {"uid": user.id},
        )
        password_reset_token_repo.conn.commit()

        assert password_reset_token_repo.complete_password_reset(
            token_id=first.id,
            user_id=user.id,
            password_hash="new-hash",
            completed_at=now,
        )
        assert not password_reset_token_repo.complete_password_reset(
            token_id=first.id,
            user_id=user.id,
            password_hash="racing-hash",
            completed_at=now,
        )

        assert user_repo.get_by_id(user.id).password_hash == "new-hash"
        keys = (
            password_reset_token_repo.conn.execute(
                text("SELECT is_login_token FROM api_keys WHERE user_id = :uid"), {"uid": user.id}
            )
            .scalars()
            .all()
        )
        assert keys == [0]
        assert password_reset_token_repo.get_by_hash("atomic-a").used_at is not None
        assert password_reset_token_repo.get_by_hash("atomic-b").used_at is not None

    def test_complete_password_reset_rolls_back_every_security_change_on_failure(
        self,
        user_repo: SQLAlchemyUserRepository,
        password_reset_token_repo: SQLAlchemyPasswordResetTokenRepository,
    ):
        self._create_api_keys_table(password_reset_token_repo)
        user = self._make_user(user_repo, email="rollback@b.com")
        now = datetime.now(UTC)
        token = password_reset_token_repo.create(
            PasswordResetToken(user_id=user.id, token_hash="rollback", expires_at=now + timedelta(hours=1))
        )
        password_reset_token_repo.conn.execute(
            text("INSERT INTO api_keys (user_id, is_login_token) VALUES (:uid, 1)"), {"uid": user.id}
        )
        password_reset_token_repo.conn.execute(
            text(
                "CREATE TRIGGER reject_password_update BEFORE UPDATE OF password_hash ON users "
                "BEGIN SELECT RAISE(FAIL, 'password update failed'); END"
            )
        )
        password_reset_token_repo.conn.commit()

        with pytest.raises(Exception, match="password update failed"):
            password_reset_token_repo.complete_password_reset(
                token_id=token.id,
                user_id=user.id,
                password_hash="new-hash",
                completed_at=now,
            )

        assert password_reset_token_repo.get_by_hash("rollback").used_at is None
        assert password_reset_token_repo.conn.execute(text("SELECT COUNT(*) FROM api_keys")).scalar_one() == 1
        assert user_repo.get_by_id(user.id).password_hash == "x"
