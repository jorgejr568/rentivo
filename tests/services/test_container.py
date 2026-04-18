from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from rentivo.services.audit_service import AuditService
from rentivo.services.authorization_service import AuthorizationService
from rentivo.services.bill_service import BillService
from rentivo.services.billing_service import BillingService
from rentivo.services.container import ConnectionServices
from rentivo.services.invite_service import InviteService
from rentivo.services.mfa_service import MFAService
from rentivo.services.organization_service import OrganizationService
from rentivo.services.theme_service import ThemeService
from rentivo.services.user_service import UserService


class TestConnectionServices:
    @patch("rentivo.services.container.open_connection")
    def test_open_uses_managed_connection_scope(self, mock_open_connection):
        conn = MagicMock()
        storage = MagicMock()
        storage_factory = MagicMock(return_value=storage)
        mock_open_connection.return_value = nullcontext(conn)

        with ConnectionServices.open(storage_factory=storage_factory) as services:
            assert services.conn is conn
            assert services.storage is storage

    def test_storage_factory_is_lazy_and_cached(self):
        storage = MagicMock()
        storage_factory = MagicMock(return_value=storage)
        services = ConnectionServices(MagicMock(), storage_factory=storage_factory)

        assert services.storage is storage
        assert services.storage is storage
        storage_factory.assert_called_once_with()

    def test_services_are_cached_and_share_dependencies(self):
        storage = MagicMock()
        services = ConnectionServices(MagicMock(), storage_factory=MagicMock(return_value=storage))

        assert services.billing_service is services.billing_service
        assert services.bill_service is services.bill_service
        assert services.theme_service is services.theme_service

        assert isinstance(services.billing_service, BillingService)
        assert isinstance(services.bill_service, BillService)
        assert isinstance(services.theme_service, ThemeService)
        assert isinstance(services.user_service, UserService)
        assert isinstance(services.organization_service, OrganizationService)
        assert isinstance(services.invite_service, InviteService)
        assert isinstance(services.authorization_service, AuthorizationService)
        assert isinstance(services.audit_service, AuditService)
        assert isinstance(services.mfa_service, MFAService)

        assert services.billing_service.repo is services.billing_repo
        assert services.billing_service.org_repo is services.organization_repo
        assert services.bill_service.bill_repo is services.bill_repo
        assert services.bill_service.receipt_repo is services.receipt_repo
        assert services.bill_service.storage is storage
        assert services.bill_service.theme_service is services.theme_service
        assert services.user_service.repo is services.user_repo
        assert services.organization_service.repo is services.organization_repo
        assert services.invite_service.invite_repo is services.invite_repo
        assert services.invite_service.org_repo is services.organization_repo
        assert services.invite_service.user_repo is services.user_repo
        assert services.authorization_service.org_repo is services.organization_repo
        assert services.audit_service.repo is services.audit_log_repo
        assert services.mfa_service.totp_repo is services.mfa_totp_repo
        assert services.mfa_service.recovery_repo is services.recovery_code_repo
        assert services.mfa_service.passkey_repo is services.passkey_repo
        assert services.mfa_service.org_repo is services.organization_repo
