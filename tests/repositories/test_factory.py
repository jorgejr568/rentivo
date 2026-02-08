from unittest.mock import MagicMock, patch

from landlord.repositories.factory import (
    get_bill_repository,
    get_billing_repository,
    get_user_repository,
)
from landlord.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyUserRepository,
)


class TestRepoFactory:
    @patch("landlord.db.get_connection")
    def test_get_billing_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_billing_repository()
        assert isinstance(repo, SQLAlchemyBillingRepository)

    @patch("landlord.db.get_connection")
    def test_get_bill_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_bill_repository()
        assert isinstance(repo, SQLAlchemyBillRepository)

    @patch("landlord.db.get_connection")
    def test_get_user_repository(self, mock_conn):
        mock_conn.return_value = MagicMock()
        repo = get_user_repository()
        assert isinstance(repo, SQLAlchemyUserRepository)
