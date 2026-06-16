from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from rentivo.jobs.backoff import backoff_seconds
    from rentivo.jobs.temporal.config import config_from_settings
    from rentivo.jobs.temporal.retry import is_permanent, should_give_up

_FINALIZE = "rentivo.finalize_job"


def _error_text(err: BaseException) -> str:
    cause = getattr(err, "cause", None) or err
    msg = getattr(cause, "message", None) or str(cause)
    return msg[:4096]


def _error_type(err: BaseException) -> str | None:
    cause = getattr(err, "cause", None)
    return getattr(cause, "type", None) if isinstance(cause, ApplicationError) else None


async def _run_job(job_type: str, payload: dict, ulid: str, max_attempts: int) -> None:
    """Shared orchestration mirroring the database worker's retry/backoff/
    dead-letter semantics. Each per-job-type workflow delegates here.

    ``job_type`` doubles as the activity name (they're registered 1:1)."""
    cfg = config_from_settings()
    attempt = 0
    while True:
        attempt += 1
        try:
            await workflow.execute_activity(
                job_type,
                payload,
                start_to_close_timeout=timedelta(seconds=cfg.activity_timeout_seconds),
                # The workflow owns retries/backoff; the activity runs once per loop.
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ActivityError as err:
            permanent = is_permanent(_error_type(err))
            error_text = _error_text(err)
            if should_give_up(attempt, max_attempts, permanent):
                await _finalize(
                    {
                        "kind": "failed",
                        "job_type": job_type,
                        "ulid": ulid,
                        "attempts": attempt,
                        "error": error_text,
                        "payload": payload,
                    }
                )
                raise
            wait = backoff_seconds(attempt)
            await _finalize(
                {
                    "kind": "retry",
                    "job_type": job_type,
                    "ulid": ulid,
                    "attempts": attempt,
                    "error": error_text,
                    "next_run_after": _now_plus_iso(wait),
                    "payload": payload,
                }
            )
            await workflow.sleep(timedelta(seconds=wait))
            continue
        else:
            await _finalize({"kind": "succeeded", "job_type": job_type, "ulid": ulid, "attempts": attempt})
            return


def _now_plus_iso(seconds: int) -> str:
    return (workflow.now() + timedelta(seconds=seconds)).isoformat()


async def _finalize(event: dict) -> None:
    await workflow.execute_activity(
        _FINALIZE,
        event,
        start_to_close_timeout=timedelta(seconds=60),
        retry_policy=RetryPolicy(maximum_attempts=3),
    )


@workflow.defn(name="EmailSendWorkflow")
class EmailSendWorkflow:
    @workflow.run
    async def run(self, payload: dict, ulid: str, max_attempts: int) -> None:
        await _run_job("email.send", payload, ulid, max_attempts)


@workflow.defn(name="CommunicationSendWorkflow")
class CommunicationSendWorkflow:
    @workflow.run
    async def run(self, payload: dict, ulid: str, max_attempts: int) -> None:
        await _run_job("communication.send", payload, ulid, max_attempts)


@workflow.defn(name="PdfRenderWorkflow")
class PdfRenderWorkflow:
    @workflow.run
    async def run(self, payload: dict, ulid: str, max_attempts: int) -> None:
        await _run_job("pdf.render", payload, ulid, max_attempts)


@workflow.defn(name="S3DeleteWorkflow")
class S3DeleteWorkflow:
    @workflow.run
    async def run(self, payload: dict, ulid: str, max_attempts: int) -> None:
        await _run_job("s3.delete", payload, ulid, max_attempts)


@workflow.defn(name="ExportGenerateWorkflow")
class ExportGenerateWorkflow:
    @workflow.run
    async def run(self, payload: dict, ulid: str, max_attempts: int) -> None:
        await _run_job("export.generate", payload, ulid, max_attempts)


@workflow.defn(name="ExportSendWorkflow")
class ExportSendWorkflow:
    @workflow.run
    async def run(self, payload: dict, ulid: str, max_attempts: int) -> None:
        await _run_job("export.send", payload, ulid, max_attempts)
