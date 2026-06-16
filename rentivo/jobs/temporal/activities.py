from __future__ import annotations

from typing import Callable

import structlog
from temporalio import activity
from temporalio.exceptions import ApplicationError

from rentivo.jobs import registry
from rentivo.jobs.base import PermanentJobError
from rentivo.jobs.temporal.retry import PERMANENT_ERROR_TYPE
from rentivo.models.audit_log import AuditEventType
from rentivo.observability import extract_context, span

logger = structlog.get_logger(__name__)

# ---- Handler execution -----------------------------------------------------


def run_registered_handler(job_type: str, payload: dict) -> None:
    """Invoke the registered handler for ``job_type`` inside a trace span that
    re-parents onto the enqueuing request (via the ``_otel`` carrier), mapping
    ``PermanentJobError`` and a missing handler to a non-retryable failure."""
    handler = registry.get(job_type)
    if handler is None:
        raise ApplicationError(
            f"no handler registered for job_type {job_type!r}",
            type=PERMANENT_ERROR_TYPE,
            non_retryable=True,
        )
    parent = extract_context(payload.get("_otel", {}))
    attributes = {"job.type": job_type}
    try:
        with span(f"job {job_type}", parent=parent, attributes=attributes):
            handler(payload)
    except PermanentJobError as exc:
        raise ApplicationError(str(exc), type=PERMANENT_ERROR_TYPE, non_retryable=True) from exc


# ---- Per-job-type activities ----------------------------------------------


@activity.defn(name="email.send")
def email_send_activity(payload: dict) -> None:
    run_registered_handler("email.send", payload)


@activity.defn(name="communication.send")
def communication_send_activity(payload: dict) -> None:
    run_registered_handler("communication.send", payload)


@activity.defn(name="pdf.render")
def pdf_render_activity(payload: dict) -> None:
    run_registered_handler("pdf.render", payload)


@activity.defn(name="recibo.render")
def recibo_render_activity(payload: dict) -> None:
    run_registered_handler("recibo.render", payload)


@activity.defn(name="s3.delete")
def s3_delete_activity(payload: dict) -> None:
    run_registered_handler("s3.delete", payload)


@activity.defn(name="export.generate")
def export_generate_activity(payload: dict) -> None:
    run_registered_handler("export.generate", payload)


@activity.defn(name="export.send")
def export_send_activity(payload: dict) -> None:
    run_registered_handler("export.send", payload)


# ---- Terminal/audit activity (mirrors Worker._audit_job + _fail) -----------

_EVENT_BY_KIND = {
    "succeeded": AuditEventType.JOB_SUCCEEDED,
    "retry": AuditEventType.JOB_RETRY_SCHEDULED,
    "failed": AuditEventType.JOB_FAILED,
}


def _open_audit() -> tuple[object, Callable[[], None]]:
    """Open a short-lived connection + AuditService. Returns ``(audit, close)``.

    Split out so unit tests can monkeypatch it without a real database.
    """
    from rentivo.db import get_engine
    from rentivo.repositories.sqlalchemy import SQLAlchemyAuditLogRepository
    from rentivo.services.audit_service import AuditService

    conn = get_engine().connect()
    return AuditService(SQLAlchemyAuditLogRepository(conn)), conn.close


def finalize_job(event: dict) -> None:
    """Record the terminal/retry audit event and, on failure, run the
    registered dead-letter fail-hook — the Temporal analogue of the DB worker's
    ``_audit_job`` + ``_fail``. ``event`` carries ``kind`` in
    {succeeded, retry, failed}, ``job_type``, ``ulid``, ``attempts``, and
    optionally ``error`` / ``next_run_after`` / ``payload``."""
    kind = event["kind"]
    new_state: dict = {
        "job_type": event["job_type"],
        "ulid": event["ulid"],
        "attempts": event["attempts"],
    }
    if "error" in event:
        new_state["error"] = event["error"]
    if "next_run_after" in event:
        new_state["next_run_after"] = event["next_run_after"]

    audit, close = _open_audit()
    try:
        audit.safe_log(
            event_type=_EVENT_BY_KIND[kind],
            source="worker",
            actor_id=None,
            actor_username="",
            entity_type="job",
            entity_uuid=event["ulid"],
            previous_state=None,
            new_state=new_state,
        )
    finally:
        close()

    if kind == "failed":
        hook = registry.get_fail_hook(event["job_type"])
        if hook is not None:
            try:
                hook(event.get("payload", {}))
            except Exception:
                logger.exception("job_fail_hook_failed", ulid=event["ulid"], job_type=event["job_type"])


@activity.defn(name="rentivo.finalize_job")
def finalize_job_activity(event: dict) -> None:
    finalize_job(event)
