from unittest.mock import MagicMock

import pytest

from rentivo.services.account_deletion_service import (
    AccountDeletionService,
    SoleOrganizationAdminError,
)


class TestAccountDeletionService:
    def setup_method(self):
        self.users = MagicMock()
        self.organizations = MagicMock()
        self.service = AccountDeletionService(self.users, self.organizations)

    def test_deletes_account_when_no_blockers(self):
        self.organizations.list_blocking_account_deletion.return_value = []
        self.users.delete_account.return_value = True

        self.service.delete_account(7)

        self.users.delete_account.assert_called_once_with(7)

    def test_raises_when_sole_admin_of_shared_organization(self):
        self.organizations.list_blocking_account_deletion.return_value = [3]

        with pytest.raises(SoleOrganizationAdminError):
            self.service.delete_account(7)
        self.users.delete_account.assert_not_called()

    def test_raises_when_user_missing(self):
        self.organizations.list_blocking_account_deletion.return_value = []
        self.users.delete_account.return_value = False

        with pytest.raises(ValueError, match="Usuário não encontrado."):
            self.service.delete_account(7)
