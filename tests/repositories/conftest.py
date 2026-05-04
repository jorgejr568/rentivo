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
from tests.conftest import FakeEncryptingBackend  # re-exported for backwards-compat

__all__ = ["FakeEncryptingBackend"]


@pytest.fixture()
def billing_repo(db_connection: Connection, encryption) -> SQLAlchemyBillingRepository:
    return SQLAlchemyBillingRepository(db_connection, encryption)


@pytest.fixture()
def bill_repo(db_connection: Connection, encryption) -> SQLAlchemyBillRepository:
    return SQLAlchemyBillRepository(db_connection, encryption)


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


@pytest.fixture()
def encryption() -> EncryptionBackend:
    return Base64Backend()
