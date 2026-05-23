"""Per-entity SQLAlchemy repository implementations.

Public API is exactly the set of SQLAlchemy*Repository classes; old
``from rentivo.repositories.sqlalchemy import …`` call sites keep working
through these re-exports.
"""

from __future__ import annotations

from rentivo.repositories._sqlalchemy_old import (
    SQLAlchemyAuditLogRepository,
    SQLAlchemyInviteRepository,
    SQLAlchemyKnownDeviceRepository,
    SQLAlchemyMFATOTPRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyPasskeyRepository,
    SQLAlchemyPasswordResetTokenRepository,
    SQLAlchemyReceiptRepository,
    SQLAlchemyRecoveryCodeRepository,
    SQLAlchemyThemeRepository,
    SQLAlchemyUserRepository,
)
from rentivo.repositories.sqlalchemy.bill import SQLAlchemyBillRepository
from rentivo.repositories.sqlalchemy.billing import SQLAlchemyBillingRepository

__all__ = [
    "SQLAlchemyAuditLogRepository",
    "SQLAlchemyBillRepository",
    "SQLAlchemyBillingRepository",
    "SQLAlchemyInviteRepository",
    "SQLAlchemyKnownDeviceRepository",
    "SQLAlchemyMFATOTPRepository",
    "SQLAlchemyOrganizationRepository",
    "SQLAlchemyPasskeyRepository",
    "SQLAlchemyPasswordResetTokenRepository",
    "SQLAlchemyReceiptRepository",
    "SQLAlchemyRecoveryCodeRepository",
    "SQLAlchemyThemeRepository",
    "SQLAlchemyUserRepository",
]
