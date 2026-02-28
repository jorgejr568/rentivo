from unittest.mock import patch

import pytest
from sqlalchemy import Connection

from rentivo.models.audit_log import AuditLog
from rentivo.repositories.sqlalchemy import SQLAlchemyAuditLogRepository


@pytest.fixture()
def audit_repo(db_connection: Connection) -> SQLAlchemyAuditLogRepository:
    return SQLAlchemyAuditLogRepository(db_connection)


def _sample_audit_log(**overrides) -> AuditLog:
    defaults = dict(
        event_type="billing.create",
        actor_id=1,
        actor_username="admin",
        source="web",
        entity_type="billing",
        entity_id=10,
        entity_uuid="abc123",
        previous_state=None,
        new_state={"name": "Apt 101"},
        metadata={"ip": "127.0.0.1"},
    )
    defaults.update(overrides)
    return AuditLog(**defaults)


class TestAuditLogRepoCRUD:
    def test_create_and_retrieve(self, audit_repo):
        log = _sample_audit_log()
        created = audit_repo.create(log)

        assert created.id is not None
        assert created.uuid != ""
        assert len(created.uuid) == 26
        assert created.event_type == "billing.create"
        assert created.actor_id == 1
        assert created.actor_username == "admin"
        assert created.source == "web"
        assert created.entity_type == "billing"
        assert created.entity_id == 10
        assert created.entity_uuid == "abc123"
        assert created.previous_state is None
        assert created.new_state == {"name": "Apt 101"}
        assert created.metadata == {"ip": "127.0.0.1"}
        assert created.created_at is not None

    def test_create_with_previous_state(self, audit_repo):
        log = _sample_audit_log(
            event_type="billing.update",
            previous_state={"name": "old"},
            new_state={"name": "new"},
        )
        created = audit_repo.create(log)
        assert created.previous_state == {"name": "old"}
        assert created.new_state == {"name": "new"}

    def test_create_with_null_new_state(self, audit_repo):
        log = _sample_audit_log(
            event_type="billing.delete",
            previous_state={"name": "Apt 101"},
            new_state=None,
        )
        created = audit_repo.create(log)
        assert created.previous_state == {"name": "Apt 101"}
        assert created.new_state is None

    def test_create_runtime_error(self, audit_repo):
        log = _sample_audit_log()
        # Save original before patching
        original_execute = (
            audit_repo.conn.execute.__wrapped__
            if hasattr(audit_repo.conn.execute, "__wrapped__")
            else audit_repo.conn.execute
        )
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:  # The SELECT after INSERT
                return type(
                    "FakeResult",
                    (),
                    {"mappings": lambda self: type("FakeMappings", (), {"fetchone": lambda self: None})()},
                )()
            return original_execute(*args, **kwargs)

        with patch.object(audit_repo, "conn") as mock_conn:
            mock_conn.execute.side_effect = side_effect
            mock_conn.commit = audit_repo.conn.commit
            with pytest.raises(RuntimeError, match="Failed to retrieve audit log"):
                audit_repo.create(log)


class TestAuditLogRepoQueries:
    def test_list_by_entity(self, audit_repo):
        audit_repo.create(_sample_audit_log(entity_type="billing", entity_id=1))
        audit_repo.create(_sample_audit_log(entity_type="billing", entity_id=1))
        audit_repo.create(_sample_audit_log(entity_type="billing", entity_id=2))

        results = audit_repo.list_by_entity("billing", 1)
        assert len(results) == 2
        for r in results:
            assert r.entity_type == "billing"
            assert r.entity_id == 1

    def test_list_by_entity_empty(self, audit_repo):
        assert audit_repo.list_by_entity("billing", 999) == []

    def test_list_by_actor(self, audit_repo):
        audit_repo.create(_sample_audit_log(actor_id=1))
        audit_repo.create(_sample_audit_log(actor_id=1))
        audit_repo.create(_sample_audit_log(actor_id=2))

        results = audit_repo.list_by_actor(1)
        assert len(results) == 2
        for r in results:
            assert r.actor_id == 1

    def test_list_by_actor_with_limit(self, audit_repo):
        for _ in range(5):
            audit_repo.create(_sample_audit_log(actor_id=1))

        results = audit_repo.list_by_actor(1, limit=3)
        assert len(results) == 3

    def test_list_by_actor_empty(self, audit_repo):
        assert audit_repo.list_by_actor(999) == []

    def test_list_recent(self, audit_repo):
        audit_repo.create(_sample_audit_log(event_type="a"))
        audit_repo.create(_sample_audit_log(event_type="b"))
        audit_repo.create(_sample_audit_log(event_type="c"))

        results = audit_repo.list_recent()
        assert len(results) == 3

    def test_list_recent_with_limit(self, audit_repo):
        for _ in range(5):
            audit_repo.create(_sample_audit_log())

        results = audit_repo.list_recent(limit=2)
        assert len(results) == 2

    def test_list_recent_empty(self, audit_repo):
        assert audit_repo.list_recent() == []

    def test_list_recent_ordered_desc(self, audit_repo):
        audit_repo.create(_sample_audit_log(event_type="first"))
        audit_repo.create(_sample_audit_log(event_type="second"))

        results = audit_repo.list_recent()
        # Most recent first
        assert results[0].event_type == "second"
        assert results[1].event_type == "first"


class TestAuditLogRowParsing:
    def test_metadata_already_dict(self):
        """Cover branch 808->811: metadata is already a dict (not a string)."""
        mock_row = {
            "id": 1,
            "uuid": "abc123",
            "event_type": "test",
            "actor_id": 1,
            "actor_username": "admin",
            "source": "web",
            "entity_type": "billing",
            "entity_id": 10,
            "entity_uuid": "xyz",
            "previous_state": None,
            "new_state": None,
            "metadata": {"already": "parsed"},
            "created_at": None,
        }
        result = SQLAlchemyAuditLogRepository._row_to_audit_log(mock_row)
        assert result.metadata == {"already": "parsed"}
