"""Tests for BillingNotificationService — extracted home of the
billing-transfer notification logic that previously lived as a private
helper in web/routes/billing.py."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from rentivo.services.billing_notification_service import BillingNotificationService


@dataclass
class _StubBilling:
    name: str


@dataclass
class _StubUser:
    id: int
    email: str


@dataclass
class _StubMember:
    user_id: int
    email: str
    role: str


class TestBillingNotificationService:
    def setup_method(self):
        self.user_service = MagicMock()
        self.org_service = MagicMock()
        self.job_service = MagicMock()
        self.service = BillingNotificationService(
            user_service=self.user_service,
            org_service=self.org_service,
            job_service=self.job_service,
        )

    def test_notifies_previous_user_owner_when_different_from_actor(self):
        self.user_service.get_by_id.return_value = _StubUser(id=99, email="prev@x.com")
        self.org_service.list_members.return_value = []

        self.service.notify_transferred(
            billing=_StubBilling(name="Apt 7"),
            previous_owner={"owner_type": "user", "owner_id": 99},
            new_org_id=1,
            actor_user_id=42,
            actor_email="actor@x.com",
        )

        assert self.job_service.enqueue.call_count == 1
        args, kwargs = self.job_service.enqueue.call_args
        assert args[0] == "email.send"
        assert args[1]["event"] == "billing_transferred"
        assert args[1]["to_email"] == "prev@x.com"
        assert args[1]["ctx"]["billing_name"] == "Apt 7"
        assert args[1]["ctx"]["recipient_role"] == "previous_owner"
        assert args[1]["ctx"]["actor_email"] == "actor@x.com"

    def test_skips_previous_owner_when_actor_is_the_previous_owner(self):
        self.user_service.get_by_id.return_value = _StubUser(id=42, email="actor@x.com")
        self.org_service.list_members.return_value = []

        self.service.notify_transferred(
            billing=_StubBilling(name="Apt 7"),
            previous_owner={"owner_type": "user", "owner_id": 42},
            new_org_id=1,
            actor_user_id=42,
            actor_email="actor@x.com",
        )
        self.job_service.enqueue.assert_not_called()

    def test_skips_previous_org_owner(self):
        self.org_service.list_members.return_value = []

        self.service.notify_transferred(
            billing=_StubBilling(name="Apt 7"),
            previous_owner={"owner_type": "organization", "owner_id": 7},
            new_org_id=8,
            actor_user_id=42,
            actor_email="actor@x.com",
        )
        self.user_service.get_by_id.assert_not_called()
        self.job_service.enqueue.assert_not_called()

    def test_notifies_destination_admins_excluding_actor(self):
        self.user_service.get_by_id.return_value = None
        self.org_service.list_members.return_value = [
            _StubMember(user_id=10, email="admin1@x.com", role="admin"),
            _StubMember(user_id=42, email="actor@x.com", role="admin"),  # actor
            _StubMember(user_id=20, email="viewer@x.com", role="viewer"),
        ]

        self.service.notify_transferred(
            billing=_StubBilling(name="Apt 7"),
            previous_owner={"owner_type": "user", "owner_id": 99},
            new_org_id=8,
            actor_user_id=42,
            actor_email="actor@x.com",
        )

        recipients = [c.args[1]["to_email"] for c in self.job_service.enqueue.call_args_list]
        assert "admin1@x.com" in recipients
        assert "actor@x.com" not in recipients
        assert "viewer@x.com" not in recipients
