from __future__ import annotations

import pytest

from rentivo.services.audit_service import AuditService
from rentivo.services.bill_service import BillService
from rentivo.services.billing_service import BillingService
from rentivo.services.invite_service import InviteService
from rentivo.services.mfa_service import MFAService
from rentivo.services.organization_service import OrganizationService
from rentivo.services.theme_service import ThemeService
from rentivo.services.user_service import UserService

_MISSING = object()


class DummyRepo:
    def __init__(self, conn=_MISSING) -> None:
        if conn is not _MISSING:
            self.conn = conn


class DummyStorage:
    pass


SERVICE_BUILDERS = [
    lambda db_conn, repo_conn: BillingService(DummyRepo(repo_conn), DummyRepo(repo_conn), db_conn=db_conn),
    lambda db_conn, repo_conn: BillService(
        DummyRepo(repo_conn),
        DummyStorage(),
        DummyRepo(repo_conn),
        db_conn=db_conn,
    ),
    lambda db_conn, repo_conn: UserService(DummyRepo(repo_conn), db_conn=db_conn),
    lambda db_conn, repo_conn: OrganizationService(DummyRepo(repo_conn), db_conn=db_conn),
    lambda db_conn, repo_conn: InviteService(
        DummyRepo(repo_conn),
        DummyRepo(repo_conn),
        DummyRepo(repo_conn),
        db_conn=db_conn,
    ),
    lambda db_conn, repo_conn: AuditService(DummyRepo(repo_conn), db_conn=db_conn),
    lambda db_conn, repo_conn: MFAService(
        DummyRepo(repo_conn),
        DummyRepo(repo_conn),
        DummyRepo(repo_conn),
        DummyRepo(repo_conn),
        db_conn=db_conn,
    ),
    lambda db_conn, repo_conn: ThemeService(DummyRepo(repo_conn), db_conn=db_conn),
]


@pytest.mark.parametrize("build_service", SERVICE_BUILDERS)
def test_transactional_services_accept_matching_connection_bindings(build_service):
    shared_conn = object()

    service = build_service(shared_conn, shared_conn)

    assert service.transactional is True


@pytest.mark.parametrize("build_service", SERVICE_BUILDERS)
def test_transactional_services_reject_mismatched_connection_bindings(build_service):
    shared_conn = object()
    other_conn = object()

    with pytest.raises(ValueError, match="same database connection"):
        build_service(shared_conn, other_conn)


def test_transactional_services_allow_test_doubles_without_conn_attribute():
    service = UserService(DummyRepo(), db_conn=object())

    assert service.transactional is True
