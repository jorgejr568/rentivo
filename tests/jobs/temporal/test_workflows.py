import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from rentivo.jobs.temporal.retry import PERMANENT_ERROR_TYPE
from rentivo.jobs.temporal.workflows import (
    CommunicationSendWorkflow,
    EmailSendWorkflow,
    PdfRenderWorkflow,
    ReciboRenderWorkflow,
    S3DeleteWorkflow,
)

TASK_QUEUE = "test-jobs"


def _make_email_activity(behavior):
    """behavior: callable(attempt:int) -> None|raises. Counts attempts."""
    state = {"n": 0}

    @activity.defn(name="email.send")
    async def email_send(payload: dict) -> None:
        state["n"] += 1
        behavior(state["n"])

    return email_send, state


def _make_finalize_sink():
    events = []

    @activity.defn(name="rentivo.finalize_job")
    async def finalize(event: dict) -> None:
        events.append(event)

    return finalize, events


async def _run(email_activity, finalize_activity, *, max_attempts=5):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[EmailSendWorkflow],
            activities=[email_activity, finalize_activity],
        ):
            return await env.client.execute_workflow(
                EmailSendWorkflow.run,
                args=[{"to": "x"}, "01ULID", max_attempts],
                id="wf-test",
                task_queue=TASK_QUEUE,
            )


@pytest.mark.asyncio
async def test_workflow_success_finalizes_succeeded():
    email, _ = _make_email_activity(lambda n: None)
    finalize, events = _make_finalize_sink()
    await _run(email, finalize)
    assert [e["kind"] for e in events] == ["succeeded"]
    assert events[0]["ulid"] == "01ULID"
    assert events[0]["attempts"] == 1


@pytest.mark.asyncio
async def test_workflow_retries_then_succeeds():
    def behavior(n):
        if n < 3:
            raise RuntimeError("transient")

    email, state = _make_email_activity(behavior)
    finalize, events = _make_finalize_sink()
    await _run(email, finalize)
    assert state["n"] == 3
    kinds = [e["kind"] for e in events]
    assert kinds == ["retry", "retry", "succeeded"]
    assert events[0]["attempts"] == 1
    assert "next_run_after" in events[0]


@pytest.mark.asyncio
async def test_workflow_permanent_failure_dead_letters_immediately():
    def behavior(n):
        raise ApplicationError("bad", type=PERMANENT_ERROR_TYPE, non_retryable=True)

    email, state = _make_email_activity(behavior)
    finalize, events = _make_finalize_sink()
    with pytest.raises(WorkflowFailureError):
        await _run(email, finalize)
    assert state["n"] == 1  # no retries
    assert [e["kind"] for e in events] == ["failed"]


@pytest.mark.asyncio
async def test_workflow_exhausts_attempts_then_dead_letters():
    email, state = _make_email_activity(lambda n: (_ for _ in ()).throw(RuntimeError("always")))
    finalize, events = _make_finalize_sink()
    with pytest.raises(WorkflowFailureError):
        await _run(email, finalize, max_attempts=3)
    assert state["n"] == 3
    assert [e["kind"] for e in events] == ["retry", "retry", "failed"]
    assert events[-1]["attempts"] == 3


def _make_named_activity(name):
    """A no-op activity registered under ``name``; counts invocations."""
    state = {"n": 0}

    @activity.defn(name=name)
    async def _act(payload: dict) -> None:
        state["n"] += 1

    return _act, state


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("wf", "activity_name"),
    [
        (CommunicationSendWorkflow, "communication.send"),
        (PdfRenderWorkflow, "pdf.render"),
        (ReciboRenderWorkflow, "recibo.render"),
        (S3DeleteWorkflow, "s3.delete"),
    ],
)
async def test_each_workflow_class_delegates_to_run_job(wf, activity_name):
    act, _ = _make_named_activity(activity_name)
    finalize, events = _make_finalize_sink()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[wf],
            activities=[act, finalize],
        ):
            await env.client.execute_workflow(
                wf.run,
                args=[{"k": "v"}, "01ULID", 5],
                id="wf-test",
                task_queue=TASK_QUEUE,
            )
    assert [e["kind"] for e in events] == ["succeeded"]
    assert events[0]["job_type"] == activity_name
