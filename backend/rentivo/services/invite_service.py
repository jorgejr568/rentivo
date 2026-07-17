from __future__ import annotations

import structlog

from rentivo.models.invite import Invite, InviteStatus
from rentivo.observability import traced
from rentivo.repositories.base import (
    InviteRepository,
    OrganizationRepository,
    UserRepository,
)

logger = structlog.get_logger(__name__)


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

    @traced("invite.send_invite")
    def send_invite(
        self,
        org_id: int,
        email: str,
        role: str,
        invited_by_user_id: int,
    ) -> Invite:
        user = self.user_repo.get_by_email(email)
        if user is None:
            logger.warning("invite_send_failed", email=email, reason="user_not_found")
            raise ValueError(f"User with email '{email}' not found")

        existing_member = self.org_repo.get_member(org_id, user.id)
        if existing_member is not None:
            logger.warning(
                "invite_send_failed",
                email=email,
                org_id=org_id,
                reason="already_member",
            )
            raise ValueError(f"User with email '{email}' is already a member")

        if self.invite_repo.has_pending_invite(org_id, user.id):
            logger.warning(
                "invite_send_failed",
                email=email,
                org_id=org_id,
                reason="pending_invite_exists",
            )
            raise ValueError(f"User with email '{email}' already has a pending invite")

        invite = Invite(
            organization_id=org_id,
            invited_user_id=user.id,
            invited_by_user_id=invited_by_user_id,
            role=role,
            status=InviteStatus.PENDING.value,
        )
        created = self.invite_repo.create(invite)
        logger.info("invite_sent", org_id=org_id, email=email, role=role)
        return created

    def _load_pending_invite(self, invite_uuid: str, user_id: int, *, action: str) -> Invite:
        """Fetch a pending invite owned by ``user_id``, raising on any mismatch.

        ``action`` ("accept" / "decline") only shapes the warning log event so
        the two call sites keep their distinct ``invite_<action>_failed`` names.
        """
        failed = f"invite_{action}_failed"
        invite = self.invite_repo.get_by_uuid(invite_uuid)
        if invite is None:
            logger.warning(failed, invite_uuid=invite_uuid, reason="not_found")
            raise ValueError("Invite not found")
        if invite.invited_user_id != user_id:
            logger.warning(failed, invite_uuid=invite_uuid, user_id=user_id, reason="unauthorized")
            raise ValueError(f"Not authorized to {action} this invite")
        if invite.status != InviteStatus.PENDING.value:
            logger.warning(failed, invite_uuid=invite_uuid, status=invite.status, reason="not_pending")
            raise ValueError("Invite is no longer pending")
        return invite

    @traced("invite.accept_invite")
    def accept_invite(self, invite_uuid: str, user_id: int) -> Invite:
        invite = self._load_pending_invite(invite_uuid, user_id, action="accept")
        self.org_repo.add_member(invite.organization_id, invite.invited_user_id, invite.role)
        self.invite_repo.update_status(invite.id, InviteStatus.ACCEPTED.value)
        logger.info("invite_accepted", invite_uuid=invite_uuid, user_id=user_id)
        return invite

    @traced("invite.decline_invite")
    def decline_invite(self, invite_uuid: str, user_id: int) -> Invite:
        invite = self._load_pending_invite(invite_uuid, user_id, action="decline")
        self.invite_repo.update_status(invite.id, InviteStatus.DECLINED.value)
        logger.info("invite_declined", invite_uuid=invite_uuid, user_id=user_id)
        return invite

    @traced("invite.list_pending")
    def list_pending(self, user_id: int) -> list[Invite]:
        result = self.invite_repo.list_pending_for_user(user_id)
        logger.debug("invites_pending_listed", user_id=user_id, count=len(result))
        return result

    @traced("invite.list_org_invites")
    def list_org_invites(self, org_id: int) -> list[Invite]:
        result = self.invite_repo.list_by_organization(org_id)
        logger.debug("invites_org_listed", org_id=org_id, count=len(result))
        return result

    @traced("invite.count_pending")
    def count_pending(self, user_id: int) -> int:
        count = self.invite_repo.count_pending_for_user(user_id)
        logger.debug("invites_pending_counted", user_id=user_id, count=count)
        return count
