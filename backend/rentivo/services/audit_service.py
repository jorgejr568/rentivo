from __future__ import annotations

import structlog

from rentivo.models.audit_log import AuditLog
from rentivo.observability import traced
from rentivo.pii_redaction import PIIKind, redact
from rentivo.repositories.base import AuditLogRepository

logger = structlog.get_logger(__name__)


class AuditService:
    def __init__(self, repo: AuditLogRepository) -> None:
        self.repo = repo

    @traced("audit.log")
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
        """Create an audit log entry. Raises on failure.

        ``actor_username`` is partial-mask redacted (``PIIKind.EMAIL``) before
        persistence and before structlog emission so plaintext emails never
        land in audit_logs or stdout.
        """
        safe_actor = redact(actor_username or "", PIIKind.EMAIL)
        audit_log = AuditLog(
            event_type=event_type,
            actor_id=actor_id,
            actor_username=safe_actor,
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
            actor_username=safe_actor,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        return result

    @traced("audit.safe_log")
    def safe_log(self, *args, **kwargs) -> AuditLog | None:
        """Create an audit log entry, swallowing any exceptions."""
        try:
            return self.log(*args, **kwargs)
        except Exception:
            logger.exception("audit_log_failed")
            return None

    @traced("audit.safe_log_for")
    def safe_log_for(self, actor, event_type, **kwargs) -> AuditLog | None:
        """Convenience wrapper that unpacks an actor object (typically a
        ``legacy_web.context.WebActor``) into ``safe_log`` kwargs. Duck-typed: any
        object exposing ``user_id`` / ``email`` / ``source`` attrs works.

        Use this from web routes instead of hand-deriving
        ``actor_id=request.session["user_id"]`` etc. on every call.
        """
        metadata = dict(kwargs.pop("metadata", None) or {})
        if getattr(actor, "api_key_uuid", None):
            metadata["api_key_uuid"] = actor.api_key_uuid
            metadata["api_key_class"] = "login" if actor.is_login_token else "integration"
        return self.safe_log(
            event_type,
            actor_id=actor.user_id,
            actor_username=actor.email,
            source=actor.source,
            metadata=metadata,
            **kwargs,
        )

    def list_by_entity(self, entity_type: str, entity_id: int) -> list[AuditLog]:
        return self.repo.list_by_entity(entity_type, entity_id)

    def list_by_actor(self, actor_id: int, limit: int = 50) -> list[AuditLog]:
        return self.repo.list_by_actor(actor_id, limit)

    def list_recent(self, limit: int = 50) -> list[AuditLog]:
        return self.repo.list_recent(limit)
