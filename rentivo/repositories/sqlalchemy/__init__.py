"""Per-entity SQLAlchemy repository implementations.

Public API is exactly the set of SQLAlchemy*Repository classes; old
``from rentivo.repositories.sqlalchemy import …`` call sites keep working
through these re-exports.
"""

from __future__ import annotations

from rentivo.repositories.sqlalchemy.audit_log import SQLAlchemyAuditLogRepository
from rentivo.repositories.sqlalchemy.auth import (
    SQLAlchemyKnownDeviceRepository,
    SQLAlchemyPasswordResetTokenRepository,
)
from rentivo.repositories.sqlalchemy.bill import SQLAlchemyBillRepository
from rentivo.repositories.sqlalchemy.billing import SQLAlchemyBillingRepository
from rentivo.repositories.sqlalchemy.billing_attachment import SQLAlchemyBillingAttachmentRepository
from rentivo.repositories.sqlalchemy.communication import (
    SQLAlchemyCommunicationRepository,
    SQLAlchemyCommunicationTemplateRepository,
)
from rentivo.repositories.sqlalchemy.expense import SQLAlchemyExpenseRepository
from rentivo.repositories.sqlalchemy.invite import SQLAlchemyInviteRepository
from rentivo.repositories.sqlalchemy.mfa import (
    SQLAlchemyMFATOTPRepository,
    SQLAlchemyPasskeyRepository,
    SQLAlchemyRecoveryCodeRepository,
)
from rentivo.repositories.sqlalchemy.organization import SQLAlchemyOrganizationRepository
from rentivo.repositories.sqlalchemy.pix_webhook_event import SQLAlchemyPixWebhookEventRepository
from rentivo.repositories.sqlalchemy.receipt import SQLAlchemyReceiptRepository
from rentivo.repositories.sqlalchemy.recipient import SQLAlchemyRecipientRepository
from rentivo.repositories.sqlalchemy.reply_to import SQLAlchemyReplyToRecipientRepository
from rentivo.repositories.sqlalchemy.theme import SQLAlchemyThemeRepository
from rentivo.repositories.sqlalchemy.user import SQLAlchemyUserRepository

__all__ = [
    "SQLAlchemyAuditLogRepository",
    "SQLAlchemyBillRepository",
    "SQLAlchemyBillingAttachmentRepository",
    "SQLAlchemyBillingRepository",
    "SQLAlchemyCommunicationRepository",
    "SQLAlchemyCommunicationTemplateRepository",
    "SQLAlchemyExpenseRepository",
    "SQLAlchemyInviteRepository",
    "SQLAlchemyKnownDeviceRepository",
    "SQLAlchemyMFATOTPRepository",
    "SQLAlchemyOrganizationRepository",
    "SQLAlchemyPixWebhookEventRepository",
    "SQLAlchemyPasskeyRepository",
    "SQLAlchemyPasswordResetTokenRepository",
    "SQLAlchemyReceiptRepository",
    "SQLAlchemyRecipientRepository",
    "SQLAlchemyRecoveryCodeRepository",
    "SQLAlchemyReplyToRecipientRepository",
    "SQLAlchemyThemeRepository",
    "SQLAlchemyUserRepository",
]
