from __future__ import annotations

import json

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.models.audit_log import AuditLog
from rentivo.observability import traced
from rentivo.repositories.base import AuditLogRepository
from rentivo.repositories.sqlalchemy._common import _now


def _decode_json(value: object) -> object:
    return json.loads(value) if isinstance(value, str) else value


class SQLAlchemyAuditLogRepository(AuditLogRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row_to_audit_log(row: RowMapping) -> AuditLog:
        return AuditLog(
            id=row["id"],
            uuid=row["uuid"],
            event_type=row["event_type"],
            actor_id=row["actor_id"],
            actor_username=row["actor_username"],
            source=row["source"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            entity_uuid=row["entity_uuid"],
            previous_state=_decode_json(row["previous_state"]),
            new_state=_decode_json(row["new_state"]),
            metadata=_decode_json(row["metadata"]),
            created_at=row["created_at"],
        )

    @traced("audit_log_repo.create")
    def create(self, audit_log: AuditLog) -> AuditLog:
        audit_uuid = str(ULID())
        now = _now()
        self.conn.execute(
            text(
                "INSERT INTO audit_logs (uuid, event_type, actor_id, actor_username, "
                "source, entity_type, entity_id, entity_uuid, previous_state, "
                "new_state, metadata, created_at) "
                "VALUES (:uuid, :event_type, :actor_id, :actor_username, "
                ":source, :entity_type, :entity_id, :entity_uuid, :previous_state, "
                ":new_state, :metadata, :created_at)"
            ),
            {
                "uuid": audit_uuid,
                "event_type": audit_log.event_type,
                "actor_id": audit_log.actor_id,
                "actor_username": audit_log.actor_username,
                "source": audit_log.source,
                "entity_type": audit_log.entity_type,
                "entity_id": audit_log.entity_id,
                "entity_uuid": audit_log.entity_uuid,
                "previous_state": json.dumps(audit_log.previous_state)
                if audit_log.previous_state is not None
                else None,
                "new_state": json.dumps(audit_log.new_state) if audit_log.new_state is not None else None,
                "metadata": json.dumps(audit_log.metadata),
                "created_at": now,
            },
        )
        self.conn.commit()

        row = (
            self.conn.execute(
                text("SELECT * FROM audit_logs WHERE uuid = :uuid"),
                {"uuid": audit_uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            raise RuntimeError(f"Failed to retrieve audit log after create (uuid={audit_uuid})")
        return self._row_to_audit_log(row)

    @traced("audit_log_repo.list_by_entity")
    def list_by_entity(self, entity_type: str, entity_id: int) -> list[AuditLog]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT * FROM audit_logs "
                    "WHERE entity_type = :entity_type AND entity_id = :entity_id "
                    "ORDER BY created_at DESC"
                ),
                {"entity_type": entity_type, "entity_id": entity_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_audit_log(row) for row in rows]

    @traced("audit_log_repo.list_by_actor")
    def list_by_actor(self, actor_id: int, limit: int = 50) -> list[AuditLog]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM audit_logs WHERE actor_id = :actor_id ORDER BY created_at DESC LIMIT :limit"),
                {"actor_id": actor_id, "limit": limit},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_audit_log(row) for row in rows]

    @traced("audit_log_repo.list_recent")
    def list_recent(self, limit: int = 50) -> list[AuditLog]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT :limit"),
                {"limit": limit},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_audit_log(row) for row in rows]
