from billing.repositories.base import BillingRepository, BillRepository


def get_billing_repository() -> BillingRepository:
    from billing.db import get_connection
    from billing.repositories.sqlalchemy import SQLAlchemyBillingRepository

    return SQLAlchemyBillingRepository(get_connection())


def get_bill_repository() -> BillRepository:
    from billing.db import get_connection
    from billing.repositories.sqlalchemy import SQLAlchemyBillRepository

    return SQLAlchemyBillRepository(get_connection())
