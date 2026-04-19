from __future__ import annotations

import structlog

from rentivo.models.organization import Organization, OrganizationMember, OrgRole
from rentivo.repositories.base import OrganizationRepository

logger = structlog.get_logger(__name__)


class OrganizationService:
    def __init__(self, repo: OrganizationRepository) -> None:
        self.repo = repo

    def create_organization(self, name: str, created_by: int) -> Organization:
        org = Organization(name=name, created_by=created_by)
        created = self.repo.create(org)
        self.repo.add_member(created.id, created_by, OrgRole.ADMIN.value)
        logger.info(
            "organization_created",
            org_id=created.id,
            name=created.name,
            created_by=created_by,
        )
        return created

    def get_by_id(self, org_id: int) -> Organization | None:
        result = self.repo.get_by_id(org_id)
        logger.debug("organization_get_by_id", org_id=org_id, found=result is not None)
        return result

    def get_by_uuid(self, uuid: str) -> Organization | None:
        result = self.repo.get_by_uuid(uuid)
        logger.debug("organization_get_by_uuid", org_uuid=uuid, found=result is not None)
        return result

    def list_user_organizations(self, user_id: int) -> list[Organization]:
        result = self.repo.list_by_user(user_id)
        logger.debug("organizations_listed_for_user", user_id=user_id, count=len(result))
        return result

    def update_organization(self, org: Organization) -> Organization:
        result = self.repo.update(org)
        logger.info("organization_updated", org_id=result.id, name=result.name)
        return result

    def delete_organization(self, org_id: int) -> None:
        self.repo.delete(org_id)
        logger.info("organization_deleted", org_id=org_id)

    def get_member(self, org_id: int, user_id: int) -> OrganizationMember | None:
        result = self.repo.get_member(org_id, user_id)
        logger.debug("org_member_get", org_id=org_id, user_id=user_id, found=result is not None)
        return result

    def list_members(self, org_id: int) -> list[OrganizationMember]:
        result = self.repo.list_members(org_id)
        logger.debug("org_members_listed", org_id=org_id, count=len(result))
        return result

    def add_member(self, org_id: int, user_id: int, role: str) -> OrganizationMember:
        return self.repo.add_member(org_id, user_id, role)

    def remove_member(self, org_id: int, user_id: int) -> None:
        self.repo.remove_member(org_id, user_id)
        logger.info("org_member_removed", org_id=org_id, user_id=user_id)

    def update_member_role(self, org_id: int, user_id: int, role: str) -> None:
        self.repo.update_member_role(org_id, user_id, role)
        logger.info("org_member_role_updated", org_id=org_id, user_id=user_id, role=role)

    def set_enforce_mfa(self, org_id: int, enforce: bool) -> Organization:
        org = self.repo.get_by_id(org_id)
        if org is None:
            raise ValueError("Organização não encontrada")
        org.enforce_mfa = enforce
        updated = self.repo.update(org)
        logger.info("org_enforce_mfa_set", org_id=org_id, enforce=enforce)
        return updated
