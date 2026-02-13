from landlord.repositories.base import (
    BillingRepository,
    BillRepository,
    InviteRepository,
    OrganizationRepository,
    UserRepository,
)


def get_billing_repository() -> BillingRepository:
    from landlord.db import get_connection
    from landlord.repositories.sqlalchemy import SQLAlchemyBillingRepository

    return SQLAlchemyBillingRepository(get_connection())


def get_bill_repository() -> BillRepository:
    from landlord.db import get_connection
    from landlord.repositories.sqlalchemy import SQLAlchemyBillRepository

    return SQLAlchemyBillRepository(get_connection())


def get_user_repository() -> UserRepository:
    from landlord.db import get_connection
    from landlord.repositories.sqlalchemy import SQLAlchemyUserRepository

    return SQLAlchemyUserRepository(get_connection())


def get_organization_repository() -> OrganizationRepository:
    from landlord.db import get_connection
    from landlord.repositories.sqlalchemy import SQLAlchemyOrganizationRepository

    return SQLAlchemyOrganizationRepository(get_connection())


def get_invite_repository() -> InviteRepository:
    from landlord.db import get_connection
    from landlord.repositories.sqlalchemy import SQLAlchemyInviteRepository

    return SQLAlchemyInviteRepository(get_connection())
