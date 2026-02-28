from __future__ import annotations

import logging

from rentivo.models.organization import Organization, OrganizationMember, OrgRole
from rentivo.repositories.base import OrganizationRepository

logger = logging.getLogger(__name__)


class OrganizationService:
    def __init__(self, repo: OrganizationRepository) -> None:
        self.repo = repo

    def create_organization(self, name: str, created_by: int) -> Organization:
        org = Organization(name=name, created_by=created_by)
        created = self.repo.create(org)
        self.repo.add_member(created.id, created_by, OrgRole.ADMIN.value)
        logger.info(
            "Organization created: id=%s name=%s by user=%s",
            created.id,
            created.name,
            created_by,
        )
        return created

    def get_by_id(self, org_id: int) -> Organization | None:
        result = self.repo.get_by_id(org_id)
        logger.debug("get_by_id org_id=%s found=%s", org_id, result is not None)
        return result

    def get_by_uuid(self, uuid: str) -> Organization | None:
        result = self.repo.get_by_uuid(uuid)
        logger.debug("get_by_uuid uuid=%s found=%s", uuid, result is not None)
        return result

    def list_user_organizations(self, user_id: int) -> list[Organization]:
        result = self.repo.list_by_user(user_id)
        logger.debug("Listed %d organizations for user=%s", len(result), user_id)
        return result

    def update_organization(self, org: Organization) -> Organization:
        result = self.repo.update(org)
        logger.info("Organization updated: id=%s name=%s", result.id, result.name)
        return result

    def delete_organization(self, org_id: int) -> None:
        self.repo.delete(org_id)
        logger.info("Organization %s soft-deleted", org_id)

    def get_member(self, org_id: int, user_id: int) -> OrganizationMember | None:
        result = self.repo.get_member(org_id, user_id)
        logger.debug("get_member org=%s user=%s found=%s", org_id, user_id, result is not None)
        return result

    def list_members(self, org_id: int) -> list[OrganizationMember]:
        result = self.repo.list_members(org_id)
        logger.debug("Listed %d members for org=%s", len(result), org_id)
        return result

    def add_member(self, org_id: int, user_id: int, role: str) -> OrganizationMember:
        return self.repo.add_member(org_id, user_id, role)

    def remove_member(self, org_id: int, user_id: int) -> None:
        self.repo.remove_member(org_id, user_id)
        logger.info("Removed user %s from org %s", user_id, org_id)

    def update_member_role(self, org_id: int, user_id: int, role: str) -> None:
        self.repo.update_member_role(org_id, user_id, role)
        logger.info("Updated role for user %s in org %s to %s", user_id, org_id, role)

    def set_enforce_mfa(self, org_id: int, enforce: bool) -> Organization:
        org = self.repo.get_by_id(org_id)
        if org is None:
            raise ValueError("Organização não encontrada")
        org.enforce_mfa = enforce
        updated = self.repo.update(org)
        logger.info("Organization %s enforce_mfa set to %s", org_id, enforce)
        return updated
