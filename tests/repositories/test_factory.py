from unittest.mock import MagicMock, patch

from rentivo.jobs.sqlalchemy import SQLAlchemyJobRepository
from rentivo.repositories.factory import (
    get_audit_log_repository,
    get_bill_repository,
    get_billing_attachment_repository,
    get_billing_repository,
    get_communication_repository,
    get_communication_template_repository,
    get_invite_repository,
    get_job_repository,
    get_known_device_repository,
    get_mfa_totp_repository,
    get_organization_repository,
    get_passkey_repository,
    get_password_reset_token_repository,
    get_receipt_repository,
    get_recipient_repository,
    get_recovery_code_repository,
    get_theme_repository,
    get_user_repository,
)
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyAuditLogRepository,
    SQLAlchemyBillingAttachmentRepository,
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyCommunicationRepository,
    SQLAlchemyCommunicationTemplateRepository,
    SQLAlchemyInviteRepository,
    SQLAlchemyKnownDeviceRepository,
    SQLAlchemyMFATOTPRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyPasskeyRepository,
    SQLAlchemyPasswordResetTokenRepository,
    SQLAlchemyReceiptRepository,
    SQLAlchemyRecipientRepository,
    SQLAlchemyRecoveryCodeRepository,
    SQLAlchemyThemeRepository,
    SQLAlchemyUserRepository,
)


class TestRepoFactory:
    @patch("rentivo.db.get_connection")
    def test_get_billing_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_billing_repository()
        assert isinstance(repo, SQLAlchemyBillingRepository)

    @patch("rentivo.db.get_connection")
    def test_get_bill_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_bill_repository()
        assert isinstance(repo, SQLAlchemyBillRepository)

    @patch("rentivo.db.get_connection")
    def test_get_user_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_user_repository()
        assert isinstance(repo, SQLAlchemyUserRepository)

    @patch("rentivo.db.get_connection")
    def test_get_organization_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_organization_repository()
        assert isinstance(repo, SQLAlchemyOrganizationRepository)

    @patch("rentivo.db.get_connection")
    def test_get_invite_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_invite_repository()
        assert isinstance(repo, SQLAlchemyInviteRepository)

    @patch("rentivo.db.get_connection")
    def test_get_receipt_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_receipt_repository()
        assert isinstance(repo, SQLAlchemyReceiptRepository)

    @patch("rentivo.db.get_connection")
    def test_get_billing_attachment_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_billing_attachment_repository()
        assert isinstance(repo, SQLAlchemyBillingAttachmentRepository)

    @patch("rentivo.db.get_connection")
    def test_get_recipient_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_recipient_repository()
        assert isinstance(repo, SQLAlchemyRecipientRepository)

    @patch("rentivo.db.get_connection")
    def test_get_communication_template_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_communication_template_repository()
        assert isinstance(repo, SQLAlchemyCommunicationTemplateRepository)

    @patch("rentivo.db.get_connection")
    def test_get_communication_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_communication_repository()
        assert isinstance(repo, SQLAlchemyCommunicationRepository)

    @patch("rentivo.db.get_connection")
    def test_get_audit_log_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_audit_log_repository()
        assert isinstance(repo, SQLAlchemyAuditLogRepository)

    @patch("rentivo.db.get_connection")
    def test_get_mfa_totp_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_mfa_totp_repository()
        assert isinstance(repo, SQLAlchemyMFATOTPRepository)

    @patch("rentivo.db.get_connection")
    def test_get_recovery_code_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_recovery_code_repository()
        assert isinstance(repo, SQLAlchemyRecoveryCodeRepository)

    @patch("rentivo.db.get_connection")
    def test_get_passkey_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_passkey_repository()
        assert isinstance(repo, SQLAlchemyPasskeyRepository)

    @patch("rentivo.db.get_connection")
    def test_get_theme_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_theme_repository()
        assert isinstance(repo, SQLAlchemyThemeRepository)

    @patch("rentivo.db.get_connection")
    def test_get_password_reset_token_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_password_reset_token_repository()
        assert isinstance(repo, SQLAlchemyPasswordResetTokenRepository)

    @patch("rentivo.db.get_connection")
    def test_get_known_device_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_known_device_repository()
        assert isinstance(repo, SQLAlchemyKnownDeviceRepository)

    @patch("rentivo.db.get_connection")
    def test_get_job_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_job_repository()
        assert isinstance(repo, SQLAlchemyJobRepository)
