from unittest.mock import MagicMock

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
        assert created_log.actor_username == "admin"
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
