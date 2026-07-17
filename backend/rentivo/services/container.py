"""Lazy per-request service container."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from rentivo.encryption.factory import get_encryption  # noqa: F401
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyAuditLogRepository,
    SQLAlchemyBillingAttachmentRepository,
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyCommunicationRepository,
    SQLAlchemyCommunicationTemplateRepository,
    SQLAlchemyExpenseRepository,
    SQLAlchemyInviteRepository,
    SQLAlchemyKnownDeviceRepository,
    SQLAlchemyMFATOTPRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyPasskeyRepository,
    SQLAlchemyPasswordResetTokenRepository,
    SQLAlchemyReceiptRepository,
    SQLAlchemyRecipientRepository,
    SQLAlchemyRecoveryCodeRepository,
    SQLAlchemyReplyToRecipientRepository,
    SQLAlchemyThemeRepository,
    SQLAlchemyUserRepository,
)
from rentivo.services.audit_service import AuditService
from rentivo.services.authorization_service import AuthorizationService
from rentivo.services.bill_service import BillService
from rentivo.services.billing_attachment_service import BillingAttachmentService
from rentivo.services.billing_notification_service import BillingNotificationService
from rentivo.services.billing_service import BillingService
from rentivo.services.billing_stats_service import BillingStatsService
from rentivo.services.communication_service import CommunicationService
from rentivo.services.expense_service import ExpenseService
from rentivo.services.google_auth_service import GoogleAuthService
from rentivo.services.invite_service import InviteService
from rentivo.services.job_service import JobService
from rentivo.services.known_device_service import KnownDeviceService
from rentivo.services.mfa_service import MFAService
from rentivo.services.organization_service import OrganizationService
from rentivo.services.password_reset_service import PasswordResetService
from rentivo.services.pix_service import PixService
from rentivo.services.recipient_service import RecipientService
from rentivo.services.storage_cleanup_service import StorageCleanupService
from rentivo.services.theme_service import ThemeService
from rentivo.services.turnstile_service import TurnstileService
from rentivo.services.user_service import UserService
from rentivo.settings import settings
from rentivo.storage.factory import get_storage

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

    from rentivo.encryption.base import EncryptionBackend


class RequestServices:
    """Lazy per-request service container."""

    def __init__(self, *, conn: Connection, encryption: EncryptionBackend) -> None:
        self._conn = conn
        self._encryption = encryption

    @cached_property
    def billing(self) -> BillingService:
        return BillingService(SQLAlchemyBillingRepository(self._conn, self._encryption))

    @cached_property
    def billing_attachment(self) -> BillingAttachmentService:
        return BillingAttachmentService(
            SQLAlchemyBillingAttachmentRepository(self._conn, self._encryption),
            get_storage(),
        )

    @cached_property
    def billing_stats(self) -> BillingStatsService:
        return BillingStatsService(
            SQLAlchemyBillRepository(self._conn, self._encryption),
            SQLAlchemyExpenseRepository(self._conn, self._encryption),
        )

    @cached_property
    def expense(self) -> ExpenseService:
        return ExpenseService(SQLAlchemyExpenseRepository(self._conn, self._encryption))

    @cached_property
    def user(self) -> UserService:
        return UserService(SQLAlchemyUserRepository(self._conn, self._encryption))

    @cached_property
    def organization(self) -> OrganizationService:
        return OrganizationService(SQLAlchemyOrganizationRepository(self._conn, self._encryption))

    @cached_property
    def theme(self) -> ThemeService:
        return ThemeService(SQLAlchemyThemeRepository(self._conn))

    @cached_property
    def pix(self) -> PixService:
        return PixService(
            SQLAlchemyUserRepository(self._conn, self._encryption),
            SQLAlchemyOrganizationRepository(self._conn, self._encryption),
        )

    @cached_property
    def invite(self) -> InviteService:
        return InviteService(
            SQLAlchemyInviteRepository(self._conn, self._encryption),
            SQLAlchemyOrganizationRepository(self._conn, self._encryption),
            SQLAlchemyUserRepository(self._conn, self._encryption),
        )

    @cached_property
    def authorization(self) -> AuthorizationService:
        return AuthorizationService(SQLAlchemyOrganizationRepository(self._conn, self._encryption))

    @cached_property
    def audit(self) -> AuditService:
        return AuditService(SQLAlchemyAuditLogRepository(self._conn))

    @cached_property
    def mfa(self) -> MFAService:
        return MFAService(
            SQLAlchemyMFATOTPRepository(self._conn, self._encryption),
            SQLAlchemyRecoveryCodeRepository(self._conn),
            SQLAlchemyPasskeyRepository(self._conn),
            SQLAlchemyOrganizationRepository(self._conn, self._encryption),
        )

    @cached_property
    def job(self) -> JobService:
        from rentivo.jobs.factory import get_job_backend

        return JobService(
            get_job_backend(self._conn),
            AuditService(SQLAlchemyAuditLogRepository(self._conn)),
        )

    @cached_property
    def known_device(self) -> KnownDeviceService:
        return KnownDeviceService(SQLAlchemyKnownDeviceRepository(self._conn))

    @cached_property
    def turnstile(self) -> TurnstileService:
        return TurnstileService(
            site_key=settings.turnstile_site_key,
            secret_key=settings.turnstile_secret_key,
            verify_url=settings.turnstile_verify_url,
        )

    @cached_property
    def google_auth(self) -> GoogleAuthService:
        return GoogleAuthService(
            enabled=settings.google_auth_enabled,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=f"{settings.public_app_url.rstrip('/')}/auth/google/callback",
        )

    @cached_property
    def password_reset(self) -> PasswordResetService:
        user_repo = SQLAlchemyUserRepository(self._conn, self._encryption)
        return PasswordResetService(
            user_repo=user_repo,
            token_repo=SQLAlchemyPasswordResetTokenRepository(self._conn),
            job_service=self.job,
            user_service=UserService(user_repo),
            public_app_url=settings.public_app_url,
        )

    @cached_property
    def bill(self) -> BillService:
        return BillService(
            SQLAlchemyBillRepository(self._conn, self._encryption),
            get_storage(),
            SQLAlchemyReceiptRepository(self._conn, self._encryption),
            theme_service=self.theme,
            pix_service=self.pix,
            job_service=self.job,
        )

    @cached_property
    def recipient(self) -> RecipientService:
        return RecipientService(SQLAlchemyRecipientRepository(self._conn, self._encryption))

    @cached_property
    def reply_to(self) -> RecipientService:
        return RecipientService(SQLAlchemyReplyToRecipientRepository(self._conn, self._encryption))

    @cached_property
    def communication(self) -> CommunicationService:
        return CommunicationService(
            communication_repo=SQLAlchemyCommunicationRepository(self._conn, self._encryption),
            template_repo=SQLAlchemyCommunicationTemplateRepository(self._conn, self._encryption),
            job_service=self.job,
        )

    @cached_property
    def storage_cleanup(self) -> StorageCleanupService:
        return StorageCleanupService(
            job_service=self.job,
            bill_repo=SQLAlchemyBillRepository(self._conn, self._encryption),
            receipt_repo=SQLAlchemyReceiptRepository(self._conn, self._encryption),
            attachment_repo=SQLAlchemyBillingAttachmentRepository(self._conn, self._encryption),
        )

    @cached_property
    def billing_notification(self) -> BillingNotificationService:
        return BillingNotificationService(
            user_service=self.user,
            org_service=self.organization,
            job_service=self.job,
        )
