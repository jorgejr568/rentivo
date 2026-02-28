from unittest.mock import MagicMock, patch

from rentivo.repositories.factory import (
    get_audit_log_repository,
    get_bill_repository,
    get_billing_repository,
    get_invite_repository,
    get_organization_repository,
    get_receipt_repository,
    get_user_repository,
)
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyAuditLogRepository,
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyInviteRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyReceiptRepository,
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
    def test_get_audit_log_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_audit_log_repository()
        assert isinstance(repo, SQLAlchemyAuditLogRepository)
