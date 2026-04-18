from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import cached_property

from sqlalchemy import Connection

from rentivo.db import open_connection
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
from rentivo.services.audit_service import AuditService
from rentivo.services.authorization_service import AuthorizationService
from rentivo.services.bill_service import BillService
from rentivo.services.billing_service import BillingService
from rentivo.services.invite_service import InviteService
from rentivo.services.mfa_service import MFAService
from rentivo.services.organization_service import OrganizationService
from rentivo.services.theme_service import ThemeService
from rentivo.services.user_service import UserService
from rentivo.storage.base import StorageBackend
from rentivo.storage.factory import get_storage


class ConnectionServices:
    def __init__(
        self,
        conn: Connection,
        *,
        storage: StorageBackend | None = None,
        storage_factory: Callable[[], StorageBackend] | None = None,
    ) -> None:
        self.conn = conn
        self._storage = storage
        self._storage_factory = storage_factory or get_storage

    @classmethod
    @contextmanager
    def open(
        cls,
        *,
        storage: StorageBackend | None = None,
        storage_factory: Callable[[], StorageBackend] | None = None,
    ) -> Iterator[ConnectionServices]:
        with open_connection() as conn:
            yield cls(conn, storage=storage, storage_factory=storage_factory)

    @property
    def storage(self) -> StorageBackend:
        if self._storage is None:
            self._storage = self._storage_factory()
        return self._storage

    @cached_property
    def billing_repo(self):
        return get_billing_repository(conn=self.conn, autocommit=False)

    @cached_property
    def bill_repo(self):
        return get_bill_repository(conn=self.conn, autocommit=False)

    @cached_property
    def user_repo(self):
        return get_user_repository(conn=self.conn, autocommit=False)

    @cached_property
    def organization_repo(self):
        return get_organization_repository(conn=self.conn, autocommit=False)

    @cached_property
    def invite_repo(self):
        return get_invite_repository(conn=self.conn, autocommit=False)

    @cached_property
    def receipt_repo(self):
        return get_receipt_repository(conn=self.conn, autocommit=False)

    @cached_property
    def audit_log_repo(self):
        return get_audit_log_repository(conn=self.conn, autocommit=False)

    @cached_property
    def mfa_totp_repo(self):
        return get_mfa_totp_repository(conn=self.conn, autocommit=False)

    @cached_property
    def recovery_code_repo(self):
        return get_recovery_code_repository(conn=self.conn, autocommit=False)

    @cached_property
    def passkey_repo(self):
        return get_passkey_repository(conn=self.conn, autocommit=False)

    @cached_property
    def theme_repo(self):
        return get_theme_repository(conn=self.conn, autocommit=False)

    @cached_property
    def billing_service(self) -> BillingService:
        return BillingService(self.billing_repo, self.organization_repo, db_conn=self.conn)

    @cached_property
    def bill_service(self) -> BillService:
        return BillService(
            self.bill_repo,
            self.storage,
            self.receipt_repo,
            theme_service=self.theme_service,
            db_conn=self.conn,
        )

    @cached_property
    def theme_service(self) -> ThemeService:
        return ThemeService(self.theme_repo, db_conn=self.conn)

    @cached_property
    def user_service(self) -> UserService:
        return UserService(self.user_repo, db_conn=self.conn)

    @cached_property
    def organization_service(self) -> OrganizationService:
        return OrganizationService(self.organization_repo, db_conn=self.conn)

    @cached_property
    def invite_service(self) -> InviteService:
        return InviteService(
            self.invite_repo,
            self.organization_repo,
            self.user_repo,
            db_conn=self.conn,
        )

    @cached_property
    def authorization_service(self) -> AuthorizationService:
        return AuthorizationService(self.organization_repo)

    @cached_property
    def audit_service(self) -> AuditService:
        return AuditService(self.audit_log_repo, db_conn=self.conn)

    @cached_property
    def mfa_service(self) -> MFAService:
        return MFAService(
            self.mfa_totp_repo,
            self.recovery_code_repo,
            self.passkey_repo,
            self.organization_repo,
            db_conn=self.conn,
        )
