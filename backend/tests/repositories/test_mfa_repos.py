import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from unittest.mock import MagicMock, call, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError

from rentivo.models.mfa import MFAFactorRemovalResult, RecoveryCode, UserPasskey, UserTOTP
from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyMFAFactorRepository,
    SQLAlchemyMFATOTPRepository,
    SQLAlchemyPasskeyRepository,
    SQLAlchemyRecoveryCodeRepository,
    SQLAlchemyUserRepository,
)
from rentivo.repositories.sqlalchemy.mfa import (
    _ENFORCING_ORG_LOCK,
    _PASSKEY_FACTORS_LOCK,
    _TOTP_FACTOR_LOCK,
    _USER_LOCK,
    _next_usage_time,
)


def _create_user(user_repo, email="mfa_user@example.com"):
    return user_repo.create(User(email=email, password_hash="hash"))


def test_next_usage_time_normalizes_naive_and_aware_values() -> None:
    naive = datetime(2026, 7, 17, 12)
    aware = datetime(2026, 7, 17, 12, tzinfo=UTC)

    with patch("rentivo.repositories.sqlalchemy.mfa._now", return_value=aware):
        next_naive = _next_usage_time(naive)
    with patch("rentivo.repositories.sqlalchemy.mfa._now", return_value=naive):
        next_aware = _next_usage_time(aware)

    assert next_naive.tzinfo is None
    assert next_naive > naive
    assert next_aware.tzinfo is UTC
    assert next_aware > aware


@pytest.fixture()
def user_repo(db_connection):
    from rentivo.encryption.base64 import Base64Backend

    return SQLAlchemyUserRepository(db_connection, Base64Backend())


@pytest.fixture()
def totp_repo(db_connection):
    from rentivo.encryption.base64 import Base64Backend

    return SQLAlchemyMFATOTPRepository(db_connection, Base64Backend())


@pytest.fixture()
def recovery_repo(db_connection):
    return SQLAlchemyRecoveryCodeRepository(db_connection)


@pytest.fixture()
def passkey_repo(db_connection):
    return SQLAlchemyPasskeyRepository(db_connection)


@pytest.fixture()
def factor_repo(db_connection):
    db_connection.execute(
        text(
            "CREATE TABLE api_keys ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, uuid VARCHAR(26) NOT NULL, "
            "user_id INTEGER NOT NULL, is_login_token BOOLEAN NOT NULL DEFAULT 0)"
        )
    )
    db_connection.commit()
    return SQLAlchemyMFAFactorRepository(db_connection)


def _insert_key(db_connection, user_id: int, uuid: str, *, is_login_token: bool) -> None:
    db_connection.execute(
        text("INSERT INTO api_keys (uuid, user_id, is_login_token) VALUES (:uuid, :user_id, :is_login_token)"),
        {"uuid": uuid, "user_id": user_id, "is_login_token": is_login_token},
    )
    db_connection.commit()


def _enforce_mfa_for(db_connection, user_id: int) -> None:
    now = datetime(2026, 7, 17, 12)
    result = db_connection.execute(
        text(
            "INSERT INTO organizations "
            "(uuid, name, created_by, enforce_mfa, created_at, updated_at) "
            "VALUES (:uuid, 'Enforced', :user_id, 1, :now, :now)"
        ),
        {"uuid": "01JENFORCED000000000000000", "user_id": user_id, "now": now},
    )
    db_connection.execute(
        text(
            "INSERT INTO organization_members (organization_id, user_id, role, created_at) "
            "VALUES (:organization_id, :user_id, 'member', :now)"
        ),
        {"organization_id": result.lastrowid, "user_id": user_id, "now": now},
    )
    db_connection.commit()


class TestMFAFactorRepository:
    @pytest.mark.parametrize(
        "statement",
        [_USER_LOCK, _ENFORCING_ORG_LOCK, _TOTP_FACTOR_LOCK, _PASSKEY_FACTORS_LOCK],
    )
    def test_policy_and_factor_reads_are_current_locking_reads_on_mysql(self, statement):
        assert "FOR UPDATE" in str(statement.compile(dialect=mysql.dialect()))

    def test_confirm_first_totp_replaces_codes_and_preserves_only_current_login(
        self,
        factor_repo,
        totp_repo,
        recovery_repo,
        user_repo,
        db_connection,
    ):
        user = _create_user(user_repo, "confirm-first-totp@example.com")
        totp_repo.create(UserTOTP(user_id=user.id, secret="SECRET", confirmed=False))
        recovery_repo.create_batch(user.id, ["old-recovery"])
        _insert_key(db_connection, user.id, "current-login", is_login_token=True)
        _insert_key(db_connection, user.id, "other-login", is_login_token=True)
        _insert_key(db_connection, user.id, "integration", is_login_token=False)

        confirmed = factor_repo.confirm_totp_and_replace_recovery_codes(
            user.id,
            ["new-recovery-1", "new-recovery-2"],
            "current-login",
        )

        assert confirmed is True
        assert totp_repo.get_by_user_id(user.id).confirmed is True
        assert [code.code_hash for code in recovery_repo.list_unused_by_user(user.id)] == [
            "new-recovery-1",
            "new-recovery-2",
        ]
        keys = db_connection.execute(text("SELECT uuid FROM api_keys ORDER BY uuid")).scalars().all()
        assert keys == ["current-login", "integration"]

    def test_confirm_totp_with_existing_passkey_preserves_other_logins(
        self,
        factor_repo,
        totp_repo,
        passkey_repo,
        user_repo,
        db_connection,
    ):
        user = _create_user(user_repo, "confirm-later-totp@example.com")
        totp_repo.create(UserTOTP(user_id=user.id, secret="SECRET", confirmed=False))
        passkey_repo.create(
            UserPasskey(user_id=user.id, credential_id="existing", public_key="public", name="Existing")
        )
        _insert_key(db_connection, user.id, "current-login", is_login_token=True)
        _insert_key(db_connection, user.id, "other-login", is_login_token=True)

        confirmed = factor_repo.confirm_totp_and_replace_recovery_codes(
            user.id,
            ["new-recovery"],
            "current-login",
        )

        assert confirmed is True
        keys = db_connection.execute(text("SELECT uuid FROM api_keys ORDER BY uuid")).scalars().all()
        assert keys == ["current-login", "other-login"]

    def test_enrollment_transitions_handle_missing_users_and_invalid_totp_state(
        self,
        factor_repo,
        totp_repo,
        user_repo,
    ):
        assert factor_repo.confirm_totp_and_replace_recovery_codes(404, ["new"], "current") is False
        assert factor_repo.replace_recovery_codes(404, ["new"]) is False
        with pytest.raises(ValueError, match="MFA user not found"):
            factor_repo.add_passkey_and_revoke_other_logins(UserPasskey(user_id=404), "current")

        user = _create_user(user_repo, "invalid-totp-state@example.com")
        assert factor_repo.confirm_totp_and_replace_recovery_codes(user.id, ["new"], "current") is False
        assert factor_repo.replace_recovery_codes(user.id, ["new"]) is False

        totp_repo.create(UserTOTP(user_id=user.id, secret="SECRET", confirmed=True))
        assert factor_repo.confirm_totp_and_replace_recovery_codes(user.id, ["new"], "current") is False

    def test_replace_recovery_codes_commits_all_new_codes(
        self,
        factor_repo,
        totp_repo,
        recovery_repo,
        user_repo,
    ):
        user = _create_user(user_repo, "replace-recovery-codes@example.com")
        totp_repo.create(UserTOTP(user_id=user.id, secret="SECRET", confirmed=True))
        recovery_repo.create_batch(user.id, ["old-recovery"])

        replaced = factor_repo.replace_recovery_codes(user.id, ["new-recovery-1", "new-recovery-2"])

        assert replaced is True
        assert [code.code_hash for code in recovery_repo.list_unused_by_user(user.id)] == [
            "new-recovery-1",
            "new-recovery-2",
        ]

    def test_add_first_passkey_preserves_current_login_and_later_factor_preserves_all_logins(
        self,
        factor_repo,
        totp_repo,
        passkey_repo,
        user_repo,
        db_connection,
    ):
        first_user = _create_user(user_repo, "first-passkey@example.com")
        _insert_key(db_connection, first_user.id, "first-current", is_login_token=True)
        _insert_key(db_connection, first_user.id, "first-other", is_login_token=True)
        _insert_key(db_connection, first_user.id, "first-integration", is_login_token=False)

        first = factor_repo.add_passkey_and_revoke_other_logins(
            UserPasskey(
                user_id=first_user.id,
                credential_id="first-credential",
                public_key="first-public-key",
                name="First",
            ),
            "first-current",
        )

        assert passkey_repo.get_by_uuid(first.uuid) == first
        first_keys = (
            db_connection.execute(
                text("SELECT uuid FROM api_keys WHERE user_id = :user_id ORDER BY uuid"),
                {"user_id": first_user.id},
            )
            .scalars()
            .all()
        )
        assert first_keys == ["first-current", "first-integration"]

        later_user = _create_user(user_repo, "later-passkey@example.com")
        totp_repo.create(UserTOTP(user_id=later_user.id, secret="SECRET", confirmed=True))
        _insert_key(db_connection, later_user.id, "later-current", is_login_token=True)
        _insert_key(db_connection, later_user.id, "later-other", is_login_token=True)

        factor_repo.add_passkey_and_revoke_other_logins(
            UserPasskey(
                user_id=later_user.id,
                credential_id="later-credential",
                public_key="later-public-key",
                name="Later",
            ),
            "later-current",
        )

        later_keys = (
            db_connection.execute(
                text("SELECT uuid FROM api_keys WHERE user_id = :user_id ORDER BY uuid"),
                {"user_id": later_user.id},
            )
            .scalars()
            .all()
        )
        assert later_keys == ["later-current", "later-other"]

    def test_totp_confirmation_failure_preserves_unconfirmed_totp_codes_and_logins(
        self,
        factor_repo,
        totp_repo,
        recovery_repo,
        user_repo,
        db_connection,
    ):
        user = _create_user(user_repo, "failed-totp-confirmation@example.com")
        totp_repo.create(UserTOTP(user_id=user.id, secret="SECRET", confirmed=False))
        recovery_repo.create_batch(user.id, ["old-recovery"])
        _insert_key(db_connection, user.id, "current-login", is_login_token=True)
        _insert_key(db_connection, user.id, "other-login", is_login_token=True)
        db_connection.execute(
            text(
                "CREATE TRIGGER fail_recovery_insert BEFORE INSERT ON user_recovery_codes "
                "WHEN NEW.code_hash = 'injected-failure' "
                "BEGIN SELECT RAISE(FAIL, 'injected recovery failure'); END"
            )
        )
        db_connection.commit()

        with pytest.raises(IntegrityError, match="injected recovery failure"):
            factor_repo.confirm_totp_and_replace_recovery_codes(
                user.id,
                ["new-recovery", "injected-failure"],
                "current-login",
            )

        assert totp_repo.get_by_user_id(user.id).confirmed is False
        assert [code.code_hash for code in recovery_repo.list_unused_by_user(user.id)] == ["old-recovery"]
        keys = db_connection.execute(text("SELECT uuid FROM api_keys ORDER BY uuid")).scalars().all()
        assert keys == ["current-login", "other-login"]

    def test_recovery_code_replacement_failure_preserves_prior_valid_codes(
        self,
        factor_repo,
        totp_repo,
        recovery_repo,
        user_repo,
        db_connection,
    ):
        user = _create_user(user_repo, "failed-recovery-replacement@example.com")
        totp_repo.create(UserTOTP(user_id=user.id, secret="SECRET", confirmed=True))
        recovery_repo.create_batch(user.id, ["old-recovery-1", "old-recovery-2"])
        db_connection.execute(
            text(
                "CREATE TRIGGER fail_recovery_insert BEFORE INSERT ON user_recovery_codes "
                "WHEN NEW.code_hash = 'injected-failure' "
                "BEGIN SELECT RAISE(FAIL, 'injected recovery failure'); END"
            )
        )
        db_connection.commit()

        with pytest.raises(IntegrityError, match="injected recovery failure"):
            factor_repo.replace_recovery_codes(
                user.id,
                ["new-recovery", "injected-failure"],
            )

        assert [code.code_hash for code in recovery_repo.list_unused_by_user(user.id)] == [
            "old-recovery-1",
            "old-recovery-2",
        ]

    def test_first_passkey_rolls_back_when_other_login_revocation_fails(
        self,
        factor_repo,
        passkey_repo,
        user_repo,
        db_connection,
    ):
        user = _create_user(user_repo, "failed-first-passkey@example.com")
        _insert_key(db_connection, user.id, "current-login", is_login_token=True)
        _insert_key(db_connection, user.id, "other-login", is_login_token=True)
        db_connection.execute(
            text(
                "CREATE TRIGGER fail_login_delete BEFORE DELETE ON api_keys "
                "WHEN OLD.uuid = 'other-login' "
                "BEGIN SELECT RAISE(FAIL, 'injected login revocation failure'); END"
            )
        )
        db_connection.commit()

        with pytest.raises(IntegrityError, match="injected login revocation failure"):
            factor_repo.add_passkey_and_revoke_other_logins(
                UserPasskey(
                    user_id=user.id,
                    credential_id="failed-credential",
                    public_key="failed-public-key",
                    name="Failed",
                ),
                "current-login",
            )

        assert passkey_repo.list_by_user(user.id) == []
        keys = db_connection.execute(text("SELECT uuid FROM api_keys ORDER BY uuid")).scalars().all()
        assert keys == ["current-login", "other-login"]

    def test_remove_totp_cleans_recovery_and_login_tokens_atomically(
        self,
        factor_repo,
        totp_repo,
        recovery_repo,
        passkey_repo,
        user_repo,
        db_connection,
    ):
        user = _create_user(user_repo, "remove-totp@example.com")
        totp_repo.create(UserTOTP(user_id=user.id, secret="SECRET", confirmed=True))
        recovery_repo.create_batch(user.id, ["recovery"])
        remaining = passkey_repo.create(
            UserPasskey(user_id=user.id, credential_id="remaining", public_key="pk", name="Remaining")
        )
        _insert_key(db_connection, user.id, "login", is_login_token=True)
        _insert_key(db_connection, user.id, "integration", is_login_token=False)

        result = factor_repo.remove_totp_and_revoke_logins(user.id)

        assert result is MFAFactorRemovalResult.REMOVED
        assert totp_repo.get_by_user_id(user.id) is None
        assert recovery_repo.list_unused_by_user(user.id) == []
        assert passkey_repo.get_by_uuid(remaining.uuid) is not None
        keys = db_connection.execute(text("SELECT uuid FROM api_keys ORDER BY uuid")).scalars().all()
        assert keys == ["integration"]

    def test_remove_totp_preserves_everything_when_it_is_the_enforced_last_factor(
        self,
        factor_repo,
        totp_repo,
        recovery_repo,
        user_repo,
        db_connection,
    ):
        user = _create_user(user_repo, "last-totp@example.com")
        totp_repo.create(UserTOTP(user_id=user.id, secret="SECRET", confirmed=True))
        recovery_repo.create_batch(user.id, ["recovery"])
        _insert_key(db_connection, user.id, "login", is_login_token=True)
        _enforce_mfa_for(db_connection, user.id)

        result = factor_repo.remove_totp_and_revoke_logins(user.id)

        assert result is MFAFactorRemovalResult.LAST_FACTOR
        assert totp_repo.get_by_user_id(user.id) is not None
        assert len(recovery_repo.list_unused_by_user(user.id)) == 1
        assert db_connection.execute(text("SELECT COUNT(*) FROM api_keys")).scalar_one() == 1

    def test_remove_passkey_keeps_totp_and_revokes_only_login_tokens(
        self,
        factor_repo,
        totp_repo,
        passkey_repo,
        user_repo,
        db_connection,
    ):
        user = _create_user(user_repo, "remove-passkey@example.com")
        totp_repo.create(UserTOTP(user_id=user.id, secret="SECRET", confirmed=True))
        target = passkey_repo.create(
            UserPasskey(user_id=user.id, credential_id="target", public_key="pk", name="Target")
        )
        _insert_key(db_connection, user.id, "login", is_login_token=True)
        _insert_key(db_connection, user.id, "integration", is_login_token=False)
        _enforce_mfa_for(db_connection, user.id)

        result = factor_repo.remove_passkey_and_revoke_logins(target.uuid, user.id)

        assert result is MFAFactorRemovalResult.REMOVED
        assert passkey_repo.get_by_uuid(target.uuid) is None
        assert totp_repo.get_by_user_id(user.id) is not None
        keys = db_connection.execute(text("SELECT uuid FROM api_keys ORDER BY uuid")).scalars().all()
        assert keys == ["integration"]

    def test_remove_passkey_rejects_missing_wrong_user_and_enforced_last_factor(
        self,
        factor_repo,
        passkey_repo,
        user_repo,
        db_connection,
    ):
        owner = _create_user(user_repo, "passkey-owner@example.com")
        other = _create_user(user_repo, "passkey-other@example.com")
        target = passkey_repo.create(UserPasskey(user_id=owner.id, credential_id="last", public_key="pk", name="Last"))
        _insert_key(db_connection, owner.id, "login", is_login_token=True)
        _enforce_mfa_for(db_connection, owner.id)

        assert factor_repo.remove_passkey_and_revoke_logins(target.uuid, other.id) is MFAFactorRemovalResult.NOT_FOUND
        assert factor_repo.remove_passkey_and_revoke_logins(target.uuid, owner.id) is MFAFactorRemovalResult.LAST_FACTOR
        assert passkey_repo.get_by_uuid(target.uuid) is not None
        assert db_connection.execute(text("SELECT COUNT(*) FROM api_keys")).scalar_one() == 1

    def test_missing_user_and_database_failure_roll_back(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = None
        repository = SQLAlchemyMFAFactorRepository(connection)

        assert repository.remove_totp_and_revoke_logins(404) is MFAFactorRemovalResult.NOT_FOUND
        assert connection.method_calls[:2] == [call.rollback(), call.execute(_USER_LOCK, {"user_id": 404})]
        assert connection.rollback.call_count == 2

        connection.reset_mock()
        connection.execute.side_effect = RuntimeError("database unavailable")
        with pytest.raises(RuntimeError, match="database unavailable"):
            repository.remove_passkey_and_revoke_logins("missing", 404)
        assert connection.method_calls[0] == call.rollback()
        assert connection.rollback.call_count == 2

    def test_missing_totp_missing_passkey_user_and_totp_failure_roll_back(self):
        connection = MagicMock()
        locked = MagicMock()
        locked.fetchone.return_value = (7,)
        missing = MagicMock()
        missing.fetchone.return_value = None
        connection.execute.side_effect = [locked, missing]
        repository = SQLAlchemyMFAFactorRepository(connection)

        assert repository.remove_totp_and_revoke_logins(7) is MFAFactorRemovalResult.NOT_FOUND
        assert connection.rollback.call_count == 2

        connection.reset_mock()
        unlocked = MagicMock()
        unlocked.fetchone.return_value = None
        connection.execute.return_value = unlocked
        connection.execute.side_effect = None
        assert repository.remove_passkey_and_revoke_logins("missing", 404) is MFAFactorRemovalResult.NOT_FOUND
        assert connection.rollback.call_count == 2

        connection.reset_mock()
        connection.execute.side_effect = RuntimeError("totp database unavailable")
        with pytest.raises(RuntimeError, match="totp database unavailable"):
            repository.remove_totp_and_revoke_logins(7)
        assert connection.rollback.call_count == 2


class TestMFATOTPRepository:
    def test_create_and_get_by_user_id(self, totp_repo, user_repo):
        user = _create_user(user_repo)
        totp = UserTOTP(user_id=user.id, secret="JBSWY3DPEHPK3PXP", confirmed=False)
        created = totp_repo.create(totp)
        assert created.id is not None
        assert created.user_id == user.id
        assert created.secret == "JBSWY3DPEHPK3PXP"
        assert created.confirmed is False
        assert created.created_at is not None

        fetched = totp_repo.get_by_user_id(user.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.secret == "JBSWY3DPEHPK3PXP"

    def test_get_by_user_id_not_found(self, totp_repo):
        assert totp_repo.get_by_user_id(9999) is None

    def test_confirm(self, totp_repo, user_repo):
        user = _create_user(user_repo)
        totp = UserTOTP(user_id=user.id, secret="JBSWY3DPEHPK3PXP", confirmed=False)
        created = totp_repo.create(totp)
        assert created.confirmed is False

        totp_repo.confirm(user.id)
        fetched = totp_repo.get_by_user_id(user.id)
        assert fetched is not None
        assert fetched.confirmed is True
        assert fetched.confirmed_at is not None

    def test_delete_by_user_id(self, totp_repo, user_repo):
        user = _create_user(user_repo)
        totp = UserTOTP(user_id=user.id, secret="JBSWY3DPEHPK3PXP", confirmed=False)
        totp_repo.create(totp)
        assert totp_repo.get_by_user_id(user.id) is not None

        totp_repo.delete_by_user_id(user.id)
        assert totp_repo.get_by_user_id(user.id) is None

    def test_delete_by_user_id_no_record(self, totp_repo):
        # Should not raise even if no record exists
        totp_repo.delete_by_user_id(9999)

    def test_create_runtime_error(self, totp_repo, user_repo):
        user = _create_user(user_repo)
        totp = UserTOTP(user_id=user.id, secret="ABCDEF", confirmed=False)
        with patch.object(totp_repo, "get_by_user_id", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve TOTP after create"):
                totp_repo.create(totp)


class TestRecoveryCodeRepository:
    def test_create_batch_and_list_unused(self, recovery_repo, user_repo):
        user = _create_user(user_repo)
        hashes = ["hash1", "hash2", "hash3"]
        recovery_repo.create_batch(user.id, hashes)

        unused = recovery_repo.list_unused_by_user(user.id)
        assert len(unused) == 3
        assert all(isinstance(c, RecoveryCode) for c in unused)
        assert {c.code_hash for c in unused} == {"hash1", "hash2", "hash3"}
        assert all(c.used_at is None for c in unused)

    def test_list_unused_by_user_empty(self, recovery_repo):
        assert recovery_repo.list_unused_by_user(9999) == []

    def test_mark_used(self, recovery_repo, user_repo):
        user = _create_user(user_repo)
        recovery_repo.create_batch(user.id, ["hash_a", "hash_b"])

        unused = recovery_repo.list_unused_by_user(user.id)
        assert len(unused) == 2

        assert recovery_repo.mark_used(unused[0].id) is True

        still_unused = recovery_repo.list_unused_by_user(user.id)
        assert len(still_unused) == 1
        assert still_unused[0].code_hash == "hash_b"

    def test_mark_used_allows_only_one_consumer(self, recovery_repo, user_repo):
        user = _create_user(user_repo)
        recovery_repo.create_batch(user.id, ["single-use-hash"])
        code = recovery_repo.list_unused_by_user(user.id)[0]

        assert recovery_repo.mark_used(code.id) is True
        assert recovery_repo.mark_used(code.id) is False
        assert recovery_repo.list_unused_by_user(user.id) == []

    def test_delete_all_by_user(self, recovery_repo, user_repo):
        user = _create_user(user_repo)
        recovery_repo.create_batch(user.id, ["h1", "h2", "h3"])
        assert len(recovery_repo.list_unused_by_user(user.id)) == 3

        recovery_repo.delete_all_by_user(user.id)
        assert recovery_repo.list_unused_by_user(user.id) == []

    def test_delete_all_by_user_no_records(self, recovery_repo):
        # Should not raise
        recovery_repo.delete_all_by_user(9999)

    def test_mark_used_does_not_affect_others(self, recovery_repo, user_repo):
        user1 = _create_user(user_repo, "user1@example.com")
        user2 = _create_user(user_repo, "user2@example.com")
        recovery_repo.create_batch(user1.id, ["h1"])
        recovery_repo.create_batch(user2.id, ["h2"])

        codes1 = recovery_repo.list_unused_by_user(user1.id)
        assert recovery_repo.mark_used(codes1[0].id) is True

        assert len(recovery_repo.list_unused_by_user(user1.id)) == 0
        assert len(recovery_repo.list_unused_by_user(user2.id)) == 1


class TestPasskeyRepository:
    def test_create_and_get_by_uuid(self, passkey_repo, user_repo):
        user = _create_user(user_repo)
        passkey = UserPasskey(
            user_id=user.id,
            credential_id="cred_abc",
            public_key="pk_xyz",
            sign_count=0,
            name="My Key",
        )
        created = passkey_repo.create(passkey)
        assert created.id is not None
        assert created.uuid != ""
        assert created.user_id == user.id
        assert created.credential_id == "cred_abc"
        assert created.public_key == "pk_xyz"
        assert created.sign_count == 0
        assert created.name == "My Key"
        assert created.created_at is not None

        fetched = passkey_repo.get_by_uuid(created.uuid)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_by_uuid_not_found(self, passkey_repo):
        assert passkey_repo.get_by_uuid("nonexistent") is None

    def test_get_by_credential_id(self, passkey_repo, user_repo):
        user = _create_user(user_repo)
        passkey = UserPasskey(
            user_id=user.id,
            credential_id="unique_cred",
            public_key="pk",
            sign_count=0,
            name="Key",
        )
        created = passkey_repo.create(passkey)

        fetched = passkey_repo.get_by_credential_id("unique_cred")
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_by_credential_id_not_found(self, passkey_repo):
        assert passkey_repo.get_by_credential_id("no_such_cred") is None

    def test_list_by_user(self, passkey_repo, user_repo):
        user = _create_user(user_repo)
        for i in range(3):
            passkey_repo.create(
                UserPasskey(
                    user_id=user.id,
                    credential_id=f"cred_{i}",
                    public_key=f"pk_{i}",
                    sign_count=0,
                    name=f"Key {i}",
                )
            )

        keys = passkey_repo.list_by_user(user.id)
        assert len(keys) == 3

    def test_list_by_user_empty(self, passkey_repo):
        assert passkey_repo.list_by_user(9999) == []

    def test_update_sign_count(self, passkey_repo, user_repo):
        user = _create_user(user_repo)
        created = passkey_repo.create(
            UserPasskey(
                user_id=user.id,
                credential_id="cred",
                public_key="pk",
                sign_count=0,
                name="Key",
            )
        )
        assert created.sign_count == 0

        assert passkey_repo.update_sign_count(created.id, 0, None, 5) is True
        fetched = passkey_repo.get_by_uuid(created.uuid)
        assert fetched.sign_count == 5
        assert fetched.last_used_at is not None

        assert passkey_repo.update_sign_count(created.id, 0, None, 6) is False
        unchanged = passkey_repo.get_by_uuid(created.uuid)
        assert unchanged.sign_count == 5
        assert unchanged.last_used_at == fetched.last_used_at

    def test_update_sign_count_allows_only_one_zero_counter_use(self, passkey_repo, user_repo):
        user = _create_user(user_repo)
        created = passkey_repo.create(
            UserPasskey(
                user_id=user.id,
                credential_id="zero-counter-cred",
                public_key="pk",
                sign_count=0,
                name="Zero Counter Key",
            )
        )

        assert passkey_repo.update_sign_count(created.id, 0, None, 0) is True
        first_use = passkey_repo.get_by_uuid(created.uuid)
        assert first_use.sign_count == 0
        assert first_use.last_used_at is not None

        assert passkey_repo.update_sign_count(created.id, 0, None, 0) is False
        second_use = passkey_repo.get_by_uuid(created.uuid)
        assert second_use.last_used_at == first_use.last_used_at

        with patch(
            "rentivo.repositories.sqlalchemy.mfa._now",
            return_value=second_use.last_used_at,
        ):
            assert (
                passkey_repo.update_sign_count(
                    created.id,
                    second_use.sign_count,
                    second_use.last_used_at,
                    0,
                )
                is True
            )

        third_use = passkey_repo.get_by_uuid(created.uuid)
        assert third_use.last_used_at > second_use.last_used_at

    def test_update_last_used(self, passkey_repo, user_repo):
        user = _create_user(user_repo)
        created = passkey_repo.create(
            UserPasskey(
                user_id=user.id,
                credential_id="cred",
                public_key="pk",
                sign_count=0,
                name="Key",
            )
        )
        assert created.last_used_at is None

        passkey_repo.update_last_used(created.id)
        fetched = passkey_repo.get_by_uuid(created.uuid)
        assert fetched.last_used_at is not None

    def test_delete(self, passkey_repo, user_repo):
        user = _create_user(user_repo)
        created = passkey_repo.create(
            UserPasskey(
                user_id=user.id,
                credential_id="cred_del",
                public_key="pk",
                sign_count=0,
                name="Delete Me",
            )
        )
        assert passkey_repo.get_by_uuid(created.uuid) is not None

        passkey_repo.delete(created.id)
        assert passkey_repo.get_by_uuid(created.uuid) is None

    def test_create_runtime_error(self, passkey_repo, user_repo):
        user = _create_user(user_repo)
        passkey = UserPasskey(
            user_id=user.id,
            credential_id="cred",
            public_key="pk",
            sign_count=0,
            name="Key",
        )
        with patch.object(passkey_repo, "get_by_uuid", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve passkey after create"):
                passkey_repo.create(passkey)

    def test_list_by_user_different_users(self, passkey_repo, user_repo):
        user1 = _create_user(user_repo, "pk_user1@example.com")
        user2 = _create_user(user_repo, "pk_user2@example.com")
        passkey_repo.create(UserPasskey(user_id=user1.id, credential_id="c1", public_key="p1", sign_count=0, name="K1"))
        passkey_repo.create(UserPasskey(user_id=user2.id, credential_id="c2", public_key="p2", sign_count=0, name="K2"))

        assert len(passkey_repo.list_by_user(user1.id)) == 1
        assert len(passkey_repo.list_by_user(user2.id)) == 1


@pytest.mark.skipif(
    not os.getenv("RENTIVO_TEST_MARIADB_URL"),
    reason="Set RENTIVO_TEST_MARIADB_URL to run the real MariaDB concurrency contract",
)
def test_parallel_zero_counter_usage_is_atomic_on_mariadb() -> None:
    engine = create_engine(os.environ["RENTIVO_TEST_MARIADB_URL"], pool_size=20, max_overflow=0)
    baseline = datetime(2026, 7, 17, 12)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS user_passkeys"))
        connection.execute(
            text(
                "CREATE TABLE user_passkeys ("
                "id INTEGER NOT NULL PRIMARY KEY, sign_count INTEGER NOT NULL, "
                "last_used_at DATETIME(6) NULL) ENGINE=InnoDB"
            )
        )
        connection.execute(
            text("INSERT INTO user_passkeys (id, sign_count, last_used_at) VALUES (1, 0, :baseline)"),
            {"baseline": baseline},
        )

    def update_usage() -> bool:
        with engine.connect() as connection:
            return SQLAlchemyPasskeyRepository(connection).update_sign_count(1, 0, baseline, 0)

    try:
        with patch("rentivo.repositories.sqlalchemy.mfa._now", return_value=baseline):
            with ThreadPoolExecutor(max_workers=20) as pool:
                results = list(pool.map(lambda _index: update_usage(), range(20)))

        assert results.count(True) == 1
        assert results.count(False) == 19
        with engine.connect() as connection:
            stored = connection.execute(text("SELECT sign_count, last_used_at FROM user_passkeys WHERE id = 1")).one()
        assert stored.sign_count == 0
        assert stored.last_used_at > baseline
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS user_passkeys"))
        engine.dispose()


@pytest.mark.skipif(
    not os.getenv("RENTIVO_TEST_MARIADB_URL"),
    reason="Set RENTIVO_TEST_MARIADB_URL to run the real MariaDB concurrency contract",
)
def test_parallel_factor_removal_uses_current_reads_after_stale_snapshots_on_mariadb() -> None:
    engine = create_engine(os.environ["RENTIVO_TEST_MARIADB_URL"], pool_size=2, max_overflow=0)
    tables = (
        "api_keys",
        "user_recovery_codes",
        "user_passkeys",
        "user_totp",
        "organization_members",
        "organizations",
        "users",
    )
    with engine.begin() as connection:
        for name in tables:
            connection.execute(text(f"DROP TABLE IF EXISTS {name}"))
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY) ENGINE=InnoDB"))
        connection.execute(
            text(
                "CREATE TABLE organizations (id INTEGER PRIMARY KEY, enforce_mfa BOOLEAN NOT NULL, "
                "deleted_at DATETIME NULL) ENGINE=InnoDB"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE organization_members (organization_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
                "INDEX ix_member_user (user_id)) ENGINE=InnoDB"
            )
        )
        connection.execute(
            text("CREATE TABLE user_totp (user_id INTEGER PRIMARY KEY, confirmed BOOLEAN NOT NULL) ENGINE=InnoDB")
        )
        connection.execute(
            text(
                "CREATE TABLE user_recovery_codes (id INTEGER PRIMARY KEY AUTO_INCREMENT, "
                "user_id INTEGER NOT NULL) ENGINE=InnoDB"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE user_passkeys (id INTEGER PRIMARY KEY, uuid VARCHAR(26) NOT NULL UNIQUE, "
                "user_id INTEGER NOT NULL, INDEX ix_passkey_user (user_id)) ENGINE=InnoDB"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE api_keys (id INTEGER PRIMARY KEY AUTO_INCREMENT, user_id INTEGER NOT NULL, "
                "is_login_token BOOLEAN NOT NULL, INDEX ix_key_user (user_id)) ENGINE=InnoDB"
            )
        )
        connection.execute(text("INSERT INTO users (id) VALUES (1)"))
        connection.execute(text("INSERT INTO organizations (id, enforce_mfa) VALUES (1, 1)"))
        connection.execute(text("INSERT INTO organization_members (organization_id, user_id) VALUES (1, 1)"))
        connection.execute(text("INSERT INTO user_totp (user_id, confirmed) VALUES (1, 1)"))
        connection.execute(text("INSERT INTO user_recovery_codes (user_id) VALUES (1)"))
        connection.execute(text("INSERT INTO user_passkeys (id, uuid, user_id) VALUES (1, 'passkey-1', 1)"))
        connection.execute(text("INSERT INTO api_keys (user_id, is_login_token) VALUES (1, 1), (1, 1)"))

    barrier = Barrier(2)

    def remove_factor(kind: str) -> MFAFactorRemovalResult:
        with engine.connect() as connection:
            connection.execute(text("SELECT confirmed FROM user_totp WHERE user_id = 1")).all()
            connection.execute(text("SELECT uuid FROM user_passkeys WHERE user_id = 1")).all()
            barrier.wait()
            repository = SQLAlchemyMFAFactorRepository(connection)
            if kind == "totp":
                return repository.remove_totp_and_revoke_logins(1)
            return repository.remove_passkey_and_revoke_logins("passkey-1", 1)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(remove_factor, ("totp", "passkey")))

        assert sorted(results) == sorted([MFAFactorRemovalResult.REMOVED, MFAFactorRemovalResult.LAST_FACTOR])
        with engine.connect() as connection:
            factor_count = connection.execute(
                text("SELECT (SELECT COUNT(*) FROM user_totp) + (SELECT COUNT(*) FROM user_passkeys)")
            ).scalar_one()
            login_count = connection.execute(text("SELECT COUNT(*) FROM api_keys")).scalar_one()
        assert factor_count == 1
        assert login_count == 0
    finally:
        with engine.begin() as connection:
            for name in tables:
                connection.execute(text(f"DROP TABLE IF EXISTS {name}"))
        engine.dispose()


class TestMFATOTPRepoEncryption:
    def test_create_encrypts_secret(self, db_connection, fake_encryption, user_repo):
        from sqlalchemy import text

        from rentivo.models.mfa import UserTOTP
        from rentivo.models.user import User
        from rentivo.repositories.sqlalchemy import SQLAlchemyMFATOTPRepository

        user = user_repo.create(User(email="alice@example.com", password_hash="x"))
        repo = SQLAlchemyMFATOTPRepository(db_connection, fake_encryption)
        repo.create(UserTOTP(user_id=user.id, secret="JBSWY3DPEHPK3PXP", confirmed=False))

        row = (
            db_connection.execute(
                text("SELECT secret FROM user_totp WHERE user_id = :uid"),
                {"uid": user.id},
            )
            .mappings()
            .fetchone()
        )
        assert row["secret"] == "fake:JBSWY3DPEHPK3PXP"

    def test_get_decrypts_secret(self, db_connection, fake_encryption, user_repo):
        from rentivo.models.mfa import UserTOTP
        from rentivo.models.user import User
        from rentivo.repositories.sqlalchemy import SQLAlchemyMFATOTPRepository

        user = user_repo.create(User(email="alice@example.com", password_hash="x"))
        repo = SQLAlchemyMFATOTPRepository(db_connection, fake_encryption)
        repo.create(UserTOTP(user_id=user.id, secret="JBSWY3DPEHPK3PXP", confirmed=False))

        fetched = repo.get_by_user_id(user.id)
        assert fetched is not None
        assert fetched.secret == "JBSWY3DPEHPK3PXP"

    def test_get_handles_legacy_plaintext(self, db_connection, fake_encryption, user_repo):
        from sqlalchemy import text

        from rentivo.models.user import User
        from rentivo.repositories.sqlalchemy import SQLAlchemyMFATOTPRepository

        user = user_repo.create(User(email="alice@example.com", password_hash="x"))
        # Insert plaintext secret directly
        db_connection.execute(
            text("INSERT INTO user_totp (user_id, secret, confirmed, created_at) VALUES (:uid, :s, 0, :now)"),
            {"uid": user.id, "s": "PLAINTEXTSECRET", "now": "2026-04-01 00:00:00"},
        )
        db_connection.commit()

        repo = SQLAlchemyMFATOTPRepository(db_connection, fake_encryption)
        fetched = repo.get_by_user_id(user.id)
        assert fetched is not None
        assert fetched.secret == "PLAINTEXTSECRET"
