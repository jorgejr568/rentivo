from rentivo.repositories.base import (
    AuditLogRepository,
    BillingRepository,
    BillRepository,
    DashboardRepository,
    InviteRepository,
    KnownDeviceRepository,
    MFATOTPRepository,
    OrganizationRepository,
    PasskeyRepository,
    PasswordResetTokenRepository,
    ReceiptRepository,
    RecoveryCodeRepository,
    ThemeRepository,
    UserRepository,
)


def get_billing_repository() -> BillingRepository:
    from rentivo.db import get_connection
    from rentivo.encryption.factory import get_encryption
    from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository

    return SQLAlchemyBillingRepository(get_connection(), get_encryption())


def get_bill_repository() -> BillRepository:
    from rentivo.db import get_connection
    from rentivo.encryption.factory import get_encryption
    from rentivo.repositories.sqlalchemy import SQLAlchemyBillRepository

    return SQLAlchemyBillRepository(get_connection(), get_encryption())


def get_user_repository() -> UserRepository:
    from rentivo.db import get_connection
    from rentivo.encryption.factory import get_encryption
    from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

    return SQLAlchemyUserRepository(get_connection(), get_encryption())


def get_organization_repository() -> OrganizationRepository:
    from rentivo.db import get_connection
    from rentivo.encryption.factory import get_encryption
    from rentivo.repositories.sqlalchemy import SQLAlchemyOrganizationRepository

    return SQLAlchemyOrganizationRepository(get_connection(), get_encryption())


def get_invite_repository() -> InviteRepository:
    from rentivo.db import get_connection
    from rentivo.encryption.factory import get_encryption
    from rentivo.repositories.sqlalchemy import SQLAlchemyInviteRepository

    return SQLAlchemyInviteRepository(get_connection(), get_encryption())


def get_receipt_repository() -> ReceiptRepository:
    from rentivo.db import get_connection
    from rentivo.encryption.factory import get_encryption
    from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

    return SQLAlchemyReceiptRepository(get_connection(), get_encryption())


def get_audit_log_repository() -> AuditLogRepository:
    from rentivo.db import get_connection
    from rentivo.repositories.sqlalchemy import SQLAlchemyAuditLogRepository

    return SQLAlchemyAuditLogRepository(get_connection())


def get_mfa_totp_repository() -> MFATOTPRepository:
    from rentivo.db import get_connection
    from rentivo.encryption.factory import get_encryption
    from rentivo.repositories.sqlalchemy import SQLAlchemyMFATOTPRepository

    return SQLAlchemyMFATOTPRepository(get_connection(), get_encryption())


def get_recovery_code_repository() -> RecoveryCodeRepository:
    from rentivo.db import get_connection
    from rentivo.repositories.sqlalchemy import SQLAlchemyRecoveryCodeRepository

    return SQLAlchemyRecoveryCodeRepository(get_connection())


def get_passkey_repository() -> PasskeyRepository:
    from rentivo.db import get_connection
    from rentivo.repositories.sqlalchemy import SQLAlchemyPasskeyRepository

    return SQLAlchemyPasskeyRepository(get_connection())


def get_theme_repository() -> ThemeRepository:
    from rentivo.db import get_connection
    from rentivo.repositories.sqlalchemy import SQLAlchemyThemeRepository

    return SQLAlchemyThemeRepository(get_connection())


def get_password_reset_token_repository() -> PasswordResetTokenRepository:
    from rentivo.db import get_connection
    from rentivo.repositories.sqlalchemy import SQLAlchemyPasswordResetTokenRepository

    return SQLAlchemyPasswordResetTokenRepository(get_connection())


def get_known_device_repository() -> KnownDeviceRepository:
    from rentivo.db import get_connection
    from rentivo.repositories.sqlalchemy import SQLAlchemyKnownDeviceRepository

    return SQLAlchemyKnownDeviceRepository(get_connection())


def get_job_repository():
    from rentivo.db import get_connection
    from rentivo.jobs.sqlalchemy import SQLAlchemyJobRepository
    from rentivo.settings import settings

    return SQLAlchemyJobRepository(
        get_connection(),
        stuck_after_seconds=settings.job_worker_stuck_after_seconds,
    )


def get_dashboard_repository() -> DashboardRepository:
    from rentivo.db import get_connection
    from rentivo.repositories.dashboard import SQLAlchemyDashboardRepository

    return SQLAlchemyDashboardRepository(get_connection())
