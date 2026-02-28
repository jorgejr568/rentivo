from unittest.mock import patch

import pytest

from rentivo.models.mfa import RecoveryCode, UserPasskey, UserTOTP
from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyMFATOTPRepository,
    SQLAlchemyPasskeyRepository,
    SQLAlchemyRecoveryCodeRepository,
    SQLAlchemyUserRepository,
)


def _create_user(user_repo, username="mfa_user"):
    return user_repo.create(User(username=username, password_hash="hash"))


@pytest.fixture()
def user_repo(db_connection):
    return SQLAlchemyUserRepository(db_connection)


@pytest.fixture()
def totp_repo(db_connection):
    return SQLAlchemyMFATOTPRepository(db_connection)


@pytest.fixture()
def recovery_repo(db_connection):
    return SQLAlchemyRecoveryCodeRepository(db_connection)


@pytest.fixture()
def passkey_repo(db_connection):
    return SQLAlchemyPasskeyRepository(db_connection)


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

        recovery_repo.mark_used(unused[0].id)

        still_unused = recovery_repo.list_unused_by_user(user.id)
        assert len(still_unused) == 1
        assert still_unused[0].code_hash == "hash_b"

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
        user1 = _create_user(user_repo, "user1")
        user2 = _create_user(user_repo, "user2")
        recovery_repo.create_batch(user1.id, ["h1"])
        recovery_repo.create_batch(user2.id, ["h2"])

        codes1 = recovery_repo.list_unused_by_user(user1.id)
        recovery_repo.mark_used(codes1[0].id)

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

        passkey_repo.update_sign_count(created.id, 5)
        fetched = passkey_repo.get_by_uuid(created.uuid)
        assert fetched.sign_count == 5

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
        user1 = _create_user(user_repo, "pk_user1")
        user2 = _create_user(user_repo, "pk_user2")
        passkey_repo.create(UserPasskey(user_id=user1.id, credential_id="c1", public_key="p1", sign_count=0, name="K1"))
        passkey_repo.create(UserPasskey(user_id=user2.id, credential_id="c2", public_key="p2", sign_count=0, name="K2"))

        assert len(passkey_repo.list_by_user(user1.id)) == 1
        assert len(passkey_repo.list_by_user(user2.id)) == 1
