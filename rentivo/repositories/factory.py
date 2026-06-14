from sqlalchemy import Connection

from rentivo.encryption.base import EncryptionBackend
from rentivo.repositories.base import (
    AuditLogRepository,
    BillingRepository,
    BillRepository,
    CommunicationRepository,
    CommunicationTemplateRepository,
    InviteRepository,
    KnownDeviceRepository,
    MFATOTPRepository,
    OrganizationRepository,
    PasskeyRepository,
    PasswordResetTokenRepository,
    ReceiptRepository,
    RecipientRepository,
    RecoveryCodeRepository,
    ThemeRepository,
    UserRepository,
)


def _connection() -> Connection:
    # Imported lazily so the active DB connection is resolved per call (and so
    # tests can patch ``rentivo.db.get_connection``).
    from rentivo.db import get_connection

    return get_connection()


def _encryption() -> EncryptionBackend:
    from rentivo.encryption.factory import get_encryption

    return get_encryption()


def get_billing_repository() -> BillingRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository

    return SQLAlchemyBillingRepository(_connection(), _encryption())


def get_bill_repository() -> BillRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyBillRepository

    return SQLAlchemyBillRepository(_connection(), _encryption())


def get_user_repository() -> UserRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

    return SQLAlchemyUserRepository(_connection(), _encryption())


def get_organization_repository() -> OrganizationRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyOrganizationRepository

    return SQLAlchemyOrganizationRepository(_connection(), _encryption())


def get_invite_repository() -> InviteRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyInviteRepository

    return SQLAlchemyInviteRepository(_connection(), _encryption())


def get_receipt_repository() -> ReceiptRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

    return SQLAlchemyReceiptRepository(_connection(), _encryption())


def get_recipient_repository() -> RecipientRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyRecipientRepository

    return SQLAlchemyRecipientRepository(_connection(), _encryption())


def get_communication_template_repository() -> CommunicationTemplateRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyCommunicationTemplateRepository

    return SQLAlchemyCommunicationTemplateRepository(_connection(), _encryption())


def get_communication_repository() -> CommunicationRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyCommunicationRepository

    return SQLAlchemyCommunicationRepository(_connection(), _encryption())


def get_audit_log_repository() -> AuditLogRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyAuditLogRepository

    return SQLAlchemyAuditLogRepository(_connection())


def get_mfa_totp_repository() -> MFATOTPRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyMFATOTPRepository

    return SQLAlchemyMFATOTPRepository(_connection(), _encryption())


def get_recovery_code_repository() -> RecoveryCodeRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyRecoveryCodeRepository

    return SQLAlchemyRecoveryCodeRepository(_connection())


def get_passkey_repository() -> PasskeyRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyPasskeyRepository

    return SQLAlchemyPasskeyRepository(_connection())


def get_theme_repository() -> ThemeRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyThemeRepository

    return SQLAlchemyThemeRepository(_connection())


def get_password_reset_token_repository() -> PasswordResetTokenRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyPasswordResetTokenRepository

    return SQLAlchemyPasswordResetTokenRepository(_connection())


def get_known_device_repository() -> KnownDeviceRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyKnownDeviceRepository

    return SQLAlchemyKnownDeviceRepository(_connection())


def get_job_repository():
    from rentivo.jobs.sqlalchemy import SQLAlchemyJobRepository
    from rentivo.settings import settings

    return SQLAlchemyJobRepository(
        _connection(),
        stuck_after_seconds=settings.job_worker_stuck_after_seconds,
    )
