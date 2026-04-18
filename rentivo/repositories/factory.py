from sqlalchemy import Connection

from rentivo.repositories.base import (
    AuditLogRepository,
    BillingRepository,
    BillRepository,
    InviteRepository,
    MFATOTPRepository,
    OrganizationRepository,
    PasskeyRepository,
    ReceiptRepository,
    RecoveryCodeRepository,
    ThemeRepository,
    UserRepository,
)


def get_billing_repository(*, conn: Connection, autocommit: bool = True) -> BillingRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository

    return SQLAlchemyBillingRepository(conn, autocommit=autocommit)


def get_bill_repository(*, conn: Connection, autocommit: bool = True) -> BillRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyBillRepository

    return SQLAlchemyBillRepository(conn, autocommit=autocommit)


def get_user_repository(*, conn: Connection, autocommit: bool = True) -> UserRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

    return SQLAlchemyUserRepository(conn, autocommit=autocommit)


def get_organization_repository(
    *,
    conn: Connection,
    autocommit: bool = True,
) -> OrganizationRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyOrganizationRepository

    return SQLAlchemyOrganizationRepository(conn, autocommit=autocommit)


def get_invite_repository(*, conn: Connection, autocommit: bool = True) -> InviteRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyInviteRepository

    return SQLAlchemyInviteRepository(conn, autocommit=autocommit)


def get_receipt_repository(*, conn: Connection, autocommit: bool = True) -> ReceiptRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

    return SQLAlchemyReceiptRepository(conn, autocommit=autocommit)


def get_audit_log_repository(
    *,
    conn: Connection,
    autocommit: bool = True,
) -> AuditLogRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyAuditLogRepository

    return SQLAlchemyAuditLogRepository(conn, autocommit=autocommit)


def get_mfa_totp_repository(
    *,
    conn: Connection,
    autocommit: bool = True,
) -> MFATOTPRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyMFATOTPRepository

    return SQLAlchemyMFATOTPRepository(conn, autocommit=autocommit)


def get_recovery_code_repository(
    *,
    conn: Connection,
    autocommit: bool = True,
) -> RecoveryCodeRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyRecoveryCodeRepository

    return SQLAlchemyRecoveryCodeRepository(conn, autocommit=autocommit)


def get_passkey_repository(
    *,
    conn: Connection,
    autocommit: bool = True,
) -> PasskeyRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyPasskeyRepository

    return SQLAlchemyPasskeyRepository(conn, autocommit=autocommit)


def get_theme_repository(*, conn: Connection, autocommit: bool = True) -> ThemeRepository:
    from rentivo.repositories.sqlalchemy import SQLAlchemyThemeRepository

    return SQLAlchemyThemeRepository(conn, autocommit=autocommit)
