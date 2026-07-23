from __future__ import annotations

import structlog

from rentivo.observability import traced
from rentivo.repositories.base import OrganizationRepository, UserRepository

logger = structlog.get_logger(__name__)


class SoleOrganizationAdminError(ValueError):
    """User is the only admin of an organization that still has members."""


class AccountDeletionService:
    def __init__(self, users: UserRepository, organizations: OrganizationRepository) -> None:
        self.users = users
        self.organizations = organizations

    @traced("account.delete_account")
    def delete_account(self, user_id: int) -> None:
        blocking = self.organizations.list_blocking_account_deletion(user_id)
        if blocking:
            raise SoleOrganizationAdminError(
                "Transfira a administração ou exclua suas organizações antes de excluir a conta."
            )
        if not self.users.delete_account(user_id):
            raise ValueError("Usuário não encontrado.")
        logger.info("account_deleted", user_id=user_id)
