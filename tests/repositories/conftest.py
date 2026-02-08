import pytest
from sqlalchemy import Connection

from landlord.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
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
