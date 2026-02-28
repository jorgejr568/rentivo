from __future__ import annotations

import logging

from rentivo.models.invite import Invite, InviteStatus
from rentivo.repositories.base import (
    InviteRepository,
    OrganizationRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)


class InviteService:
    def __init__(
        self,
        invite_repo: InviteRepository,
        org_repo: OrganizationRepository,
        user_repo: UserRepository,
    ) -> None:
        self.invite_repo = invite_repo
        self.org_repo = org_repo
        self.user_repo = user_repo

    def send_invite(
        self,
        org_id: int,
        username: str,
        role: str,
        invited_by_user_id: int,
    ) -> Invite:
        user = self.user_repo.get_by_username(username)
        if user is None:
            logger.warning("Invite failed: user '%s' not found", username)
            raise ValueError(f"User '{username}' not found")

        existing_member = self.org_repo.get_member(org_id, user.id)
        if existing_member is not None:
            logger.warning("Invite failed: user '%s' already a member of org=%s", username, org_id)
            raise ValueError(f"User '{username}' is already a member")

        if self.invite_repo.has_pending_invite(org_id, user.id):
            logger.warning(
                "Invite failed: user '%s' already has pending invite for org=%s",
                username,
                org_id,
            )
            raise ValueError(f"User '{username}' already has a pending invite")

        invite = Invite(
            organization_id=org_id,
            invited_user_id=user.id,
            invited_by_user_id=invited_by_user_id,
            role=role,
            status=InviteStatus.PENDING.value,
        )
        created = self.invite_repo.create(invite)
        logger.info("Invite sent: org=%s user=%s role=%s", org_id, username, role)
        return created

    def accept_invite(self, invite_uuid: str, user_id: int) -> None:
        invite = self.invite_repo.get_by_uuid(invite_uuid)
        if invite is None:
            logger.warning("Accept invite failed: uuid=%s not found", invite_uuid)
            raise ValueError("Invite not found")
        if invite.invited_user_id != user_id:
            logger.warning(
                "Accept invite failed: uuid=%s user=%s not authorized",
                invite_uuid,
                user_id,
            )
            raise ValueError("Not authorized to accept this invite")
        if invite.status != InviteStatus.PENDING.value:
            logger.warning("Accept invite failed: uuid=%s status=%s", invite_uuid, invite.status)
            raise ValueError("Invite is no longer pending")

        self.org_repo.add_member(invite.organization_id, invite.invited_user_id, invite.role)
        self.invite_repo.update_status(invite.id, InviteStatus.ACCEPTED.value)
        logger.info("Invite accepted: uuid=%s user=%s", invite_uuid, user_id)

    def decline_invite(self, invite_uuid: str, user_id: int) -> None:
        invite = self.invite_repo.get_by_uuid(invite_uuid)
        if invite is None:
            logger.warning("Decline invite failed: uuid=%s not found", invite_uuid)
            raise ValueError("Invite not found")
        if invite.invited_user_id != user_id:
            logger.warning(
                "Decline invite failed: uuid=%s user=%s not authorized",
                invite_uuid,
                user_id,
            )
            raise ValueError("Not authorized to decline this invite")
        if invite.status != InviteStatus.PENDING.value:
            logger.warning("Decline invite failed: uuid=%s status=%s", invite_uuid, invite.status)
            raise ValueError("Invite is no longer pending")

        self.invite_repo.update_status(invite.id, InviteStatus.DECLINED.value)
        logger.info("Invite declined: uuid=%s user=%s", invite_uuid, user_id)

    def list_pending(self, user_id: int) -> list[Invite]:
        result = self.invite_repo.list_pending_for_user(user_id)
        logger.debug("Listed %d pending invites for user=%s", len(result), user_id)
        return result

    def list_org_invites(self, org_id: int) -> list[Invite]:
        result = self.invite_repo.list_by_organization(org_id)
        logger.debug("Listed %d invites for org=%s", len(result), org_id)
        return result

    def count_pending(self, user_id: int) -> int:
        count = self.invite_repo.count_pending_for_user(user_id)
        logger.debug("Counted %d pending invites for user=%s", count, user_id)
        return count
