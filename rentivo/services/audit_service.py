from __future__ import annotations

import structlog

from rentivo.models.audit_log import AuditLog
from rentivo.repositories.base import AuditLogRepository

logger = structlog.get_logger(__name__)


class AuditService:
    def __init__(self, repo: AuditLogRepository) -> None:
        self.repo = repo

    def log(
        self,
        event_type: str,
        *,
        actor_id: int | None = None,
        actor_username: str = "",
        source: str = "",
        entity_type: str = "",
        entity_id: int | None = None,
        entity_uuid: str = "",
        previous_state: dict | None = None,
        new_state: dict | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        """Create an audit log entry. Raises on failure."""
        audit_log = AuditLog(
            event_type=event_type,
            actor_id=actor_id,
            actor_username=actor_username,
            source=source,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_uuid=entity_uuid,
            previous_state=previous_state,
            new_state=new_state,
            metadata=metadata or {},
        )
        result = self.repo.create(audit_log)
        logger.info(
            "audit_logged",
            event_type=event_type,
            actor_id=actor_id,
            actor_username=actor_username,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        return result

    def safe_log(self, *args, **kwargs) -> AuditLog | None:
        """Create an audit log entry, swallowing any exceptions."""
        try:
            return self.log(*args, **kwargs)
        except Exception:
            logger.exception("audit_log_failed")
            return None

    def list_by_entity(self, entity_type: str, entity_id: int) -> list[AuditLog]:
        return self.repo.list_by_entity(entity_type, entity_id)

    def list_by_actor(self, actor_id: int, limit: int = 50) -> list[AuditLog]:
        return self.repo.list_by_actor(actor_id, limit)

    def list_recent(self, limit: int = 50) -> list[AuditLog]:
        return self.repo.list_recent(limit)
