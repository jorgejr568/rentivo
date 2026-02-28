import pytest
from sqlalchemy import Connection

from rentivo.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyInviteRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyUserRepository,
)


@pytest.fixture()
def billing_repo(db_connection: Connection) -> SQLAlchemyBillingRepository:
    return SQLAlchemyBillingRepository(db_connection)


@pytest.fixture()
def bill_repo(db_connection: Connection) -> SQLAlchemyBillRepository:
    return SQLAlchemyBillRepository(db_connection)


@pytest.fixture()
def user_repo(db_connection: Connection) -> SQLAlchemyUserRepository:
    return SQLAlchemyUserRepository(db_connection)


@pytest.fixture()
def org_repo(db_connection: Connection) -> SQLAlchemyOrganizationRepository:
    return SQLAlchemyOrganizationRepository(db_connection)


@pytest.fixture()
def invite_repo(db_connection: Connection) -> SQLAlchemyInviteRepository:
    return SQLAlchemyInviteRepository(db_connection)
