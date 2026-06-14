from __future__ import annotations

from datetime import datetime

import structlog

from rentivo.jobs.base import Job, JobRepository
from rentivo.models.audit_log import AuditEventType
from rentivo.observability import inject_context, traced
from rentivo.services.audit_serializers import serialize_job_payload
from rentivo.services.audit_service import AuditService

logger = structlog.get_logger(__name__)


class JobService:
    def __init__(self, repo: JobRepository, audit: AuditService) -> None:
        self.repo = repo
        self.audit = audit

    @traced("job.enqueue")
    def enqueue(
        self,
        job_type: str,
        payload: dict,
        *,
        run_after: datetime | None = None,
        max_attempts: int = 5,
        source: str = "",
        actor_id: int | None = None,
        actor_username: str = "",
    ) -> Job:
        carrier: dict = {}
        inject_context(carrier)
        enqueue_payload = {**payload, "_otel": carrier} if carrier else payload
        job = self.repo.enqueue(job_type, enqueue_payload, run_after, max_attempts)
        # Audit records the business payload only — the _otel carrier is transport.
        new_state = serialize_job_payload({"job_type": job_type, **payload})
        new_state["job_type"] = job_type
        new_state["ulid"] = job.ulid
        new_state["attempts"] = 0
        self.audit.safe_log(
            event_type=AuditEventType.JOB_ENQUEUED,
            source=source,
            actor_id=actor_id,
            actor_username=actor_username,
            entity_type="job",
            entity_uuid=job.ulid,
            previous_state=None,
            new_state=new_state,
        )
        logger.info("job_enqueued", job_type=job_type, ulid=job.ulid)
        return job

    @traced("job.enqueue_for")
    def enqueue_for(
        self,
        actor,
        job_type: str,
        payload: dict,
        *,
        run_after: datetime | None = None,
        max_attempts: int = 5,
    ) -> Job:
        """Convenience wrapper that unpacks an actor object (typically a
        ``web.context.WebActor``) into ``enqueue`` kwargs. Duck-typed.
        """
        return self.enqueue(
            job_type,
            payload,
            run_after=run_after,
            max_attempts=max_attempts,
            source=actor.source,
            actor_id=actor.user_id,
            actor_username=actor.email,
        )
