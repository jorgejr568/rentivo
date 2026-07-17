from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from rentivo.models.audit_log import AuditEventType, AuditLog
from rentivo.services.audit_service import AuditService


class TestAuditServiceLog:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.service = AuditService(self.mock_repo)

    def test_log_creates_entry(self):
        self.mock_repo.create.return_value = AuditLog(
            id=1,
            uuid="abc123",
            event_type=AuditEventType.BILLING_CREATE,
            actor_id=1,
            actor_username="admin",
            source="web",
            entity_type="billing",
            entity_id=10,
        )

        result = self.service.log(
            AuditEventType.BILLING_CREATE,
            actor_id=1,
            actor_username="admin",
            source="web",
            entity_type="billing",
            entity_id=10,
            entity_uuid="xyz",
            new_state={"name": "Apt 101"},
        )

        assert result.event_type == AuditEventType.BILLING_CREATE
        self.mock_repo.create.assert_called_once()
        created_log = self.mock_repo.create.call_args[0][0]
        assert created_log.event_type == "billing.create"
        assert created_log.actor_id == 1
        assert created_log.actor_username == "***"  # "admin" has no '@' → redacted to ***
        assert created_log.source == "web"
        assert created_log.entity_type == "billing"
        assert created_log.entity_id == 10
        assert created_log.entity_uuid == "xyz"
        assert created_log.new_state == {"name": "Apt 101"}
        assert created_log.previous_state is None
        assert created_log.metadata == {}

    def test_log_with_metadata(self):
        self.mock_repo.create.return_value = AuditLog(id=1, event_type="test", metadata={"ip": "1.2.3.4"})
        self.service.log(
            "test",
            metadata={"ip": "1.2.3.4"},
        )
        created_log = self.mock_repo.create.call_args[0][0]
        assert created_log.metadata == {"ip": "1.2.3.4"}

    def test_log_with_both_states(self):
        self.mock_repo.create.return_value = AuditLog(id=1, event_type="billing.update")
        self.service.log(
            AuditEventType.BILLING_UPDATE,
            previous_state={"name": "old"},
            new_state={"name": "new"},
        )
        created_log = self.mock_repo.create.call_args[0][0]
        assert created_log.previous_state == {"name": "old"}
        assert created_log.new_state == {"name": "new"}

    def test_log_recursively_redacts_credentials_before_persistence(self):
        self.mock_repo.create.side_effect = lambda log: log

        result = self.service.log(
            "api_key.used",
            previous_state={"credentials": [{"password": "old-password"}]},
            new_state={"session": {"loginToken": "login-secret"}},
            metadata={
                "api_key_uuid": "01SAFEKEYUUID",
                "api_key_class": "integration",
                "source": "api",
                "key_hint": "rntv-v1-abcd...yz",
                "nested": ({"Authorization": "Bearer token-value"},),
                "provider": {
                    "client_secret": "client-secret",
                    "error": "id_token=oidc-secret recovery_code=recovery-secret",
                },
            },
        )

        assert result.previous_state == {"credentials": [{"password": "[REDACTED]"}]}
        assert result.new_state == {"session": {"loginToken": "[REDACTED]"}}
        assert result.metadata == {
            "api_key_uuid": "01SAFEKEYUUID",
            "api_key_class": "integration",
            "source": "api",
            "key_hint": "rntv-v1-abcd...yz",
            "nested": ({"Authorization": "[REDACTED]"},),
            "provider": {
                "client_secret": "[REDACTED]",
                "error": "id_token=[REDACTED] recovery_code=[REDACTED]",
            },
        }

    def test_log_defaults(self):
        self.mock_repo.create.return_value = AuditLog(id=1, event_type="test")
        self.service.log("test")
        created_log = self.mock_repo.create.call_args[0][0]
        assert created_log.actor_id is None
        assert created_log.actor_username == ""
        assert created_log.source == ""
        assert created_log.entity_type == ""
        assert created_log.entity_id is None
        assert created_log.entity_uuid == ""
        assert created_log.previous_state is None
        assert created_log.new_state is None
        assert created_log.metadata == {}


class TestAuditServiceSafeLog:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.service = AuditService(self.mock_repo)

    def test_safe_log_success(self):
        self.mock_repo.create.return_value = AuditLog(id=1, event_type="test")
        result = self.service.safe_log("test")
        assert result is not None
        assert result.event_type == "test"

    def test_safe_log_swallows_exceptions(self):
        self.mock_repo.create.side_effect = RuntimeError("DB error")
        result = self.service.safe_log("test")
        assert result is None

    def test_safe_log_passes_args(self):
        self.mock_repo.create.return_value = AuditLog(id=1, event_type="billing.create")
        self.service.safe_log(
            AuditEventType.BILLING_CREATE,
            actor_id=5,
            actor_username="admin",
            source="web",
        )
        created_log = self.mock_repo.create.call_args[0][0]
        assert created_log.event_type == "billing.create"
        assert created_log.actor_id == 5


class TestAuditServiceQueries:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.service = AuditService(self.mock_repo)

    def test_list_by_entity(self):
        self.mock_repo.list_by_entity.return_value = [
            AuditLog(id=1, event_type="billing.create"),
        ]
        result = self.service.list_by_entity("billing", 1)
        assert len(result) == 1
        self.mock_repo.list_by_entity.assert_called_once_with("billing", 1)

    def test_list_by_actor(self):
        self.mock_repo.list_by_actor.return_value = [
            AuditLog(id=1, event_type="billing.create"),
        ]
        result = self.service.list_by_actor(1, limit=10)
        assert len(result) == 1
        self.mock_repo.list_by_actor.assert_called_once_with(1, 10)

    def test_list_recent(self):
        self.mock_repo.list_recent.return_value = [
            AuditLog(id=1, event_type="billing.create"),
            AuditLog(id=2, event_type="billing.update"),
        ]
        result = self.service.list_recent(limit=25)
        assert len(result) == 2
        self.mock_repo.list_recent.assert_called_once_with(25)

    def test_list_recent_default_limit(self):
        self.mock_repo.list_recent.return_value = []
        self.service.list_recent()
        self.mock_repo.list_recent.assert_called_once_with(50)


class TestActorUsernameRedaction:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.mock_repo.create.side_effect = lambda log: log
        self.service = AuditService(self.mock_repo)

    def test_log_redacts_email_in_actor_username(self):
        result = self.service.log(
            event_type="user.login",
            actor_id=1,
            actor_username="alice@example.com",
        )
        assert result.actor_username == "al...@example.com"

    def test_log_keeps_empty_actor_username(self):
        result = self.service.log(event_type="user.login", actor_username="")
        assert result.actor_username == ""

    def test_log_masks_non_email_username(self):
        # If a non-email is ever passed, the PIIKind.EMAIL masker collapses it
        # (no '@' is treated as a "short" value → ***). This is defensive — CLI
        # source already uses actor_username="" — but verify the masker isn't
        # leaking the raw value.
        result = self.service.log(event_type="job.scheduled", actor_username="cli")
        assert result.actor_username == "***"


class TestSafeLogFor:
    """Tests for safe_log_for — the WebActor-unpacking convenience wrapper."""

    def setup_method(self):
        self.mock_repo = MagicMock()
        self.mock_repo.create.side_effect = lambda log: log
        self.service = AuditService(self.mock_repo)

    def test_safe_log_for_unpacks_actor(self):
        from legacy_web.context import WebActor

        actor = WebActor(user_id=42, email="alice@example.com")
        result = self.service.safe_log_for(
            actor,
            AuditEventType.BILLING_CREATE,
            entity_type="billing",
            entity_id=1,
            new_state={"name": "Apt 1"},
        )
        assert result is not None
        created_log = self.mock_repo.create.call_args[0][0]
        assert created_log.actor_id == 42
        # actor_username is post-redaction; "alice@example.com" → "al...@example.com"
        assert created_log.actor_username == "al...@example.com"
        assert created_log.source == "web"
        assert created_log.entity_type == "billing"
        assert created_log.entity_id == 1

    @pytest.mark.parametrize(("is_login_token", "key_class"), [(True, "login"), (False, "integration")])
    def test_safe_log_for_preserves_api_key_attribution(self, is_login_token, key_class):
        actor = SimpleNamespace(
            user_id=42,
            email="alice@example.com",
            source="api",
            api_key_uuid="01SAFEKEYUUID",
            is_login_token=is_login_token,
        )

        self.service.safe_log_for(actor, "api.request", metadata={"request_id": "request-123"})

        created_log = self.mock_repo.create.call_args[0][0]
        assert created_log.source == "api"
        assert created_log.metadata == {
            "request_id": "request-123",
            "api_key_uuid": "01SAFEKEYUUID",
            "api_key_class": key_class,
        }

    def test_safe_log_for_anon_actor(self):
        from legacy_web.context import ANON_ACTOR

        self.service.safe_log_for(
            ANON_ACTOR,
            AuditEventType.USER_LOGIN_FAILED,
            entity_type="user",
            entity_id=None,
            new_state={"email": "h...@x.com"},
        )
        created_log = self.mock_repo.create.call_args[0][0]
        assert created_log.actor_id is None
        assert created_log.actor_username == ""
        assert created_log.source == "web"

    def test_safe_log_for_swallows_exceptions(self):
        from legacy_web.context import WebActor

        self.mock_repo.create.side_effect = RuntimeError("DB down")
        result = self.service.safe_log_for(
            WebActor(user_id=1, email="x@y.z"),
            "test.event",
        )
        assert result is None
