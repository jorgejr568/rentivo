import pytest
from sqlalchemy import Connection

from rentivo.encryption.base import EncryptionBackend
from rentivo.encryption.base64 import Base64Backend
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyInviteRepository,
    SQLAlchemyKnownDeviceRepository,
    SQLAlchemyMFATOTPRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyPasswordResetTokenRepository,
    SQLAlchemyThemeRepository,
    SQLAlchemyUserRepository,
)


@pytest.fixture()
def billing_repo(db_connection: Connection, encryption) -> SQLAlchemyBillingRepository:
    return SQLAlchemyBillingRepository(db_connection, encryption)


@pytest.fixture()
def bill_repo(db_connection: Connection) -> SQLAlchemyBillRepository:
    return SQLAlchemyBillRepository(db_connection)


@pytest.fixture()
def user_repo(db_connection: Connection, encryption) -> SQLAlchemyUserRepository:
    return SQLAlchemyUserRepository(db_connection, encryption)


@pytest.fixture()
def org_repo(db_connection: Connection, encryption) -> SQLAlchemyOrganizationRepository:
    return SQLAlchemyOrganizationRepository(db_connection, encryption)


@pytest.fixture()
def invite_repo(db_connection: Connection) -> SQLAlchemyInviteRepository:
    return SQLAlchemyInviteRepository(db_connection)


@pytest.fixture()
def theme_repo(db_connection: Connection) -> SQLAlchemyThemeRepository:
    return SQLAlchemyThemeRepository(db_connection)


@pytest.fixture()
def password_reset_token_repo(db_connection: Connection) -> SQLAlchemyPasswordResetTokenRepository:
    return SQLAlchemyPasswordResetTokenRepository(db_connection)


@pytest.fixture()
def known_device_repo(db_connection: Connection) -> SQLAlchemyKnownDeviceRepository:
    return SQLAlchemyKnownDeviceRepository(db_connection)


@pytest.fixture()
def mfa_totp_repo(db_connection: Connection, encryption) -> SQLAlchemyMFATOTPRepository:
    return SQLAlchemyMFATOTPRepository(db_connection, encryption)


class FakeEncryptingBackend(EncryptionBackend):
    """Test double that prefixes/strips ``fake:`` so we can assert the repo
    actually routed values through encrypt/decrypt. Distinct prefix from both
    Base64Backend (``b64:v1:``) and KMSBackend (``enc:v1:``) so its ciphertext
    is unambiguous in test assertions."""

    PREFIX = "fake:"

    def encrypt(self, plaintext: str) -> str:
        if plaintext == "":
            return ""
        if self.is_encrypted(plaintext):
            return plaintext
        return self.PREFIX + plaintext

    def decrypt(self, value: str) -> str:
        if value == "":
            return ""
        if not self.is_encrypted(value):
            return value
        return value[len(self.PREFIX) :]

    def is_encrypted(self, value: str) -> bool:
        return value.startswith(self.PREFIX)


@pytest.fixture()
def encryption() -> EncryptionBackend:
    return Base64Backend()


@pytest.fixture()
def fake_encryption() -> FakeEncryptingBackend:
    return FakeEncryptingBackend()
