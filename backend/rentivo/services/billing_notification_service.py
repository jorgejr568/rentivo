"""Email notifications for billing-ownership changes.

Billing transfer notification delivery belongs in the service layer so
API route modules share one implementation.
"""

from __future__ import annotations

import structlog

from rentivo.models.organization import OrgRole
from rentivo.observability import traced

logger = structlog.get_logger(__name__)


class BillingNotificationService:
    def __init__(self, *, user_service, org_service, job_service) -> None:
        self._user_service = user_service
        self._org_service = org_service
        self._job_service = job_service

    @traced("billing_notification.notify_transferred")
    def notify_transferred(
        self,
        *,
        billing,
        previous_owner: dict,
        new_org_id: int,
        actor_user_id: int,
        actor_email: str,
    ) -> None:
        """Email the previous user-owner (if any, not the actor) plus
        every admin of the destination org (excluding the actor)."""
        if previous_owner.get("owner_type") == "user":
            prev_user = self._user_service.get_by_id(previous_owner["owner_id"])
            if prev_user is not None and prev_user.id != actor_user_id:
                self._enqueue(
                    to_email=prev_user.email,
                    billing_name=billing.name,
                    recipient_role="previous_owner",
                    actor_email=actor_email,
                    actor_user_id=actor_user_id,
                )

        for member in self._org_service.list_members(new_org_id):
            if member.user_id == actor_user_id:
                continue
            if member.role == OrgRole.ADMIN.value:
                self._enqueue(
                    to_email=member.email,
                    billing_name=billing.name,
                    recipient_role="destination_admin",
                    actor_email=actor_email,
                    actor_user_id=actor_user_id,
                )

    def _enqueue(
        self,
        *,
        to_email: str,
        billing_name: str,
        recipient_role: str,
        actor_email: str,
        actor_user_id: int,
    ) -> None:
        self._job_service.enqueue(
            "email.send",
            {
                "event": "billing_transferred",
                "to_email": to_email,
                "ctx": {
                    "billing_name": billing_name,
                    "recipient_role": recipient_role,
                    "actor_email": actor_email,
                },
            },
            source="web",
            actor_id=actor_user_id,
            actor_username=actor_email,
        )
