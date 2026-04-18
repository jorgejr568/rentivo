from unittest.mock import MagicMock

import pytest

from rentivo.repositories.factory import (
    get_audit_log_repository,
    get_bill_repository,
    get_billing_repository,
    get_invite_repository,
    get_mfa_totp_repository,
    get_organization_repository,
    get_passkey_repository,
    get_receipt_repository,
    get_recovery_code_repository,
    get_theme_repository,
    get_user_repository,
)
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyAuditLogRepository,
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyInviteRepository,
    SQLAlchemyMFATOTPRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyPasskeyRepository,
    SQLAlchemyReceiptRepository,
    SQLAlchemyRecoveryCodeRepository,
    SQLAlchemyThemeRepository,
    SQLAlchemyUserRepository,
)


class TestRepoFactory:
    def test_get_billing_repository(self):
        repo = get_billing_repository(conn=MagicMock())
        assert isinstance(repo, SQLAlchemyBillingRepository)

    def test_get_billing_repository_autocommit_override(self):
        repo = get_billing_repository(conn=MagicMock(), autocommit=False)
        assert isinstance(repo, SQLAlchemyBillingRepository)
        assert repo.autocommit is False

    def test_get_bill_repository(self):
        repo = get_bill_repository(conn=MagicMock())
        assert isinstance(repo, SQLAlchemyBillRepository)

    def test_get_bill_repository_autocommit_override(self):
        repo = get_bill_repository(conn=MagicMock(), autocommit=False)
        assert isinstance(repo, SQLAlchemyBillRepository)
        assert repo.autocommit is False

    def test_get_user_repository(self):
        repo = get_user_repository(conn=MagicMock())
        assert isinstance(repo, SQLAlchemyUserRepository)

    def test_get_user_repository_autocommit_override(self):
        repo = get_user_repository(conn=MagicMock(), autocommit=False)
        assert isinstance(repo, SQLAlchemyUserRepository)
        assert repo.autocommit is False

    def test_get_organization_repository(self):
        repo = get_organization_repository(conn=MagicMock())
        assert isinstance(repo, SQLAlchemyOrganizationRepository)

    def test_get_organization_repository_autocommit_override(self):
        repo = get_organization_repository(conn=MagicMock(), autocommit=False)
        assert isinstance(repo, SQLAlchemyOrganizationRepository)
        assert repo.autocommit is False

    def test_get_invite_repository(self):
        repo = get_invite_repository(conn=MagicMock())
        assert isinstance(repo, SQLAlchemyInviteRepository)

    def test_get_invite_repository_autocommit_override(self):
        repo = get_invite_repository(conn=MagicMock(), autocommit=False)
        assert isinstance(repo, SQLAlchemyInviteRepository)
        assert repo.autocommit is False

    def test_get_receipt_repository(self):
        repo = get_receipt_repository(conn=MagicMock())
        assert isinstance(repo, SQLAlchemyReceiptRepository)

    def test_get_receipt_repository_autocommit_override(self):
        repo = get_receipt_repository(conn=MagicMock(), autocommit=False)
        assert isinstance(repo, SQLAlchemyReceiptRepository)
        assert repo.autocommit is False

    def test_get_audit_log_repository(self):
        repo = get_audit_log_repository(conn=MagicMock())
        assert isinstance(repo, SQLAlchemyAuditLogRepository)

    def test_get_audit_log_repository_autocommit_override(self):
        repo = get_audit_log_repository(conn=MagicMock(), autocommit=False)
        assert isinstance(repo, SQLAlchemyAuditLogRepository)
        assert repo.autocommit is False

    def test_get_mfa_totp_repository(self):
        repo = get_mfa_totp_repository(conn=MagicMock())
        assert isinstance(repo, SQLAlchemyMFATOTPRepository)

    def test_get_mfa_totp_repository_autocommit_override(self):
        repo = get_mfa_totp_repository(conn=MagicMock(), autocommit=False)
        assert isinstance(repo, SQLAlchemyMFATOTPRepository)
        assert repo.autocommit is False

    def test_get_recovery_code_repository(self):
        repo = get_recovery_code_repository(conn=MagicMock())
        assert isinstance(repo, SQLAlchemyRecoveryCodeRepository)

    def test_get_recovery_code_repository_autocommit_override(self):
        repo = get_recovery_code_repository(conn=MagicMock(), autocommit=False)
        assert isinstance(repo, SQLAlchemyRecoveryCodeRepository)
        assert repo.autocommit is False

    def test_get_passkey_repository(self):
        repo = get_passkey_repository(conn=MagicMock())
        assert isinstance(repo, SQLAlchemyPasskeyRepository)

    def test_get_passkey_repository_autocommit_override(self):
        repo = get_passkey_repository(conn=MagicMock(), autocommit=False)
        assert isinstance(repo, SQLAlchemyPasskeyRepository)
        assert repo.autocommit is False

    def test_get_theme_repository(self):
        repo = get_theme_repository(conn=MagicMock())
        assert isinstance(repo, SQLAlchemyThemeRepository)

    def test_get_theme_repository_autocommit_override(self):
        repo = get_theme_repository(conn=MagicMock(), autocommit=False)
        assert isinstance(repo, SQLAlchemyThemeRepository)
        assert repo.autocommit is False

    @pytest.mark.parametrize(
        ("factory", "repo_type"),
        [
            (get_billing_repository, SQLAlchemyBillingRepository),
            (get_bill_repository, SQLAlchemyBillRepository),
            (get_user_repository, SQLAlchemyUserRepository),
            (get_organization_repository, SQLAlchemyOrganizationRepository),
            (get_invite_repository, SQLAlchemyInviteRepository),
            (get_receipt_repository, SQLAlchemyReceiptRepository),
            (get_audit_log_repository, SQLAlchemyAuditLogRepository),
            (get_mfa_totp_repository, SQLAlchemyMFATOTPRepository),
            (get_recovery_code_repository, SQLAlchemyRecoveryCodeRepository),
            (get_passkey_repository, SQLAlchemyPasskeyRepository),
            (get_theme_repository, SQLAlchemyThemeRepository),
        ],
    )
    def test_repository_factory_uses_explicit_connection(self, factory, repo_type):
        explicit_conn = MagicMock()
        repo = factory(conn=explicit_conn)

        assert isinstance(repo, repo_type)
        assert repo.conn is explicit_conn

    @pytest.mark.parametrize(
        "factory",
        [
            get_billing_repository,
            get_bill_repository,
            get_user_repository,
            get_organization_repository,
            get_invite_repository,
            get_receipt_repository,
            get_audit_log_repository,
            get_mfa_totp_repository,
            get_recovery_code_repository,
            get_passkey_repository,
            get_theme_repository,
        ],
    )
    def test_repository_factory_requires_explicit_connection(self, factory):
        with pytest.raises(TypeError, match="required keyword-only argument: 'conn'"):
            factory()
