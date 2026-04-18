from __future__ import annotations

import logging

from sqlalchemy import Connection

from rentivo.models.billing import Billing, BillingItem
from rentivo.models.organization import OrgRole
from rentivo.repositories.base import BillingRepository, OrganizationRepository
from rentivo.services._transaction import validate_transaction_binding

logger = logging.getLogger(__name__)

ORG_BILLING_MANAGER_ROLES = {OrgRole.ADMIN.value, OrgRole.MANAGER.value}


class BillingService:
    def __init__(
        self,
        repo: BillingRepository,
        org_repo: OrganizationRepository | None = None,
        db_conn: Connection | None = None,
    ) -> None:
        self.repo = repo
        self.org_repo = org_repo
        self.db_conn = db_conn
        validate_transaction_binding(self.db_conn, self.repo, self.org_repo)

    @property
    def transactional(self) -> bool:
        return self.db_conn is not None

    def _commit_transaction(self) -> None:
        if self.db_conn is not None:
            self.db_conn.commit()

    def _rollback_transaction(self) -> None:
        if self.db_conn is not None:
            self.db_conn.rollback()

    def _validate_owner_access(self, owner_type: str, owner_id: int, actor_user_id: int | None) -> None:
        """Validate ownership changes when the caller identity is known."""
        if owner_type == "user":
            if actor_user_id is not None and owner_id != actor_user_id:
                logger.warning("Billing ownership validation failed: actor=%s target_user=%s", actor_user_id, owner_id)
                raise ValueError("Cannot create a personal billing for another user")
            return

        if owner_type != "organization":
            logger.warning("Billing ownership validation failed: invalid owner_type=%s", owner_type)
            raise ValueError("Invalid billing owner type")

        if actor_user_id is None or self.org_repo is None:
            return

        org = self.org_repo.get_by_id(owner_id)
        if org is None:
            logger.warning("Billing ownership validation failed: organization %s not found", owner_id)
            raise ValueError("Organization not found")

        member = self.org_repo.get_member(owner_id, actor_user_id)
        if member is None or member.role not in ORG_BILLING_MANAGER_ROLES:
            logger.warning(
                "Billing ownership validation failed: actor=%s org=%s role=%s",
                actor_user_id,
                owner_id,
                member.role if member else None,
            )
            raise ValueError("You do not have permission to manage billings for this organization")

    def create_billing(
        self,
        name: str,
        description: str,
        items: list[BillingItem],
        pix_key: str = "",
        owner_type: str = "user",
        owner_id: int = 0,
        actor_user_id: int | None = None,
    ) -> Billing:
        self._validate_owner_access(owner_type, owner_id, actor_user_id)
        billing = Billing(
            name=name,
            description=description,
            items=items,
            pix_key=pix_key,
            owner_type=owner_type,
            owner_id=owner_id,
        )
        try:
            result = self.repo.create(billing)
            if self.transactional:
                self._commit_transaction()
        except Exception:
            if self.transactional:
                self._rollback_transaction()
            raise
        logger.info("Billing created: id=%s, name=%s", result.id, result.name)
        return result

    def list_billings(self) -> list[Billing]:
        result = self.repo.list_all()
        logger.debug("Listed %d billings (all)", len(result))
        return result

    def list_billings_for_user(self, user_id: int) -> list[Billing]:
        result = self.repo.list_for_user(user_id)
        logger.debug("Listed %d billings for user=%s", len(result), user_id)
        return result

    def get_billing(self, billing_id: int) -> Billing | None:
        result = self.repo.get_by_id(billing_id)
        logger.debug("get_billing id=%s found=%s", billing_id, result is not None)
        return result

    def get_billing_by_uuid(self, uuid: str) -> Billing | None:
        result = self.repo.get_by_uuid(uuid)
        logger.debug("get_billing_by_uuid uuid=%s found=%s", uuid, result is not None)
        return result

    def update_billing(self, billing: Billing) -> Billing:
        try:
            result = self.repo.update(billing)
            if self.transactional:
                self._commit_transaction()
        except Exception:
            if self.transactional:
                self._rollback_transaction()
            raise
        logger.info("Billing updated: id=%s, name=%s", result.id, result.name)
        return result

    def delete_billing(self, billing_id: int) -> None:
        try:
            self.repo.delete(billing_id)
            if self.transactional:
                self._commit_transaction()
        except Exception:
            if self.transactional:
                self._rollback_transaction()
            raise
        logger.info("Billing %s soft-deleted", billing_id)

    def transfer_to_organization(self, billing_id: int, org_id: int, actor_user_id: int | None = None) -> None:
        billing = self.repo.get_by_id(billing_id)
        if billing is None:
            logger.warning("Transfer failed: billing %s not found", billing_id)
            raise ValueError("Billing not found")
        if billing.owner_type != "user":
            logger.warning("Transfer failed: billing %s is not user-owned", billing_id)
            raise ValueError("Only personal billings can be transferred to organizations")
        self._validate_owner_access("organization", org_id, actor_user_id)
        try:
            self.repo.transfer_owner(billing_id, "organization", org_id)
            if self.transactional:
                self._commit_transaction()
        except Exception:
            if self.transactional:
                self._rollback_transaction()
            raise
        logger.info("Billing %s transferred to organization %s", billing_id, org_id)
