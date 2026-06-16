from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from rentivo.jobs.base import Job
from rentivo.jobs.temporal import backend as backend_mod
from rentivo.jobs.temporal.backend import TemporalJobBackend, _start_delay, build_temporal_backend
from rentivo.jobs.temporal.config import TemporalConfig
from rentivo.jobs.temporal.workflows import EmailSendWorkflow


@pytest.fixture
def cfg():
    return TemporalConfig(host="h:7233", namespace="ns", task_queue="q", tls=False, activity_timeout_seconds=600)


def test_enqueue_starts_the_mapped_workflow(cfg):
    bridge = MagicMock()
    client = MagicMock()
    bridge.run.side_effect = [client, "HANDLE"]  # ensure_client, then start_workflow
    be = TemporalJobBackend(cfg, bridge=bridge, connect=lambda c: "ignored")

    job = be.enqueue("email.send", {"to": "x", "_otel": {}}, max_attempts=4)

    assert isinstance(job, Job)
    assert job.job_type == "email.send"
    assert job.max_attempts == 4
    assert job.ulid  # generated
    # second bridge.run call carries the start_workflow coroutine; assert it was made
    assert bridge.run.call_count == 2


def test_enqueue_unknown_job_type_raises(cfg):
    be = TemporalJobBackend(cfg, bridge=MagicMock(), connect=lambda c: None)
    with pytest.raises(ValueError, match="no Temporal workflow"):
        be.enqueue("does.not.exist", {})


def test_workflow_map_covers_all_handlers():
    assert set(backend_mod._WORKFLOW_BY_TYPE) == {
        "email.send",
        "communication.send",
        "pdf.render",
        "s3.delete",
        "export.generate",
        "export.send",
    }
    assert backend_mod._WORKFLOW_BY_TYPE["email.send"] is EmailSendWorkflow


def test_start_delay_none_when_no_run_after():
    assert _start_delay(None) is None


def test_start_delay_positive_for_future_run_after():
    delay = _start_delay(datetime.now(UTC) + timedelta(hours=1))
    assert delay is not None
    assert delay.total_seconds() > 0


def test_start_delay_none_for_past_run_after():
    assert _start_delay(datetime.now(UTC) - timedelta(hours=1)) is None


def test_build_temporal_backend_is_singleton(monkeypatch):
    monkeypatch.setattr(backend_mod, "_singleton", None)
    monkeypatch.setattr(backend_mod, "TemporalJobBackend", lambda *a, **k: object())
    a = build_temporal_backend()
    b = build_temporal_backend()
    assert a is b
    monkeypatch.setattr(backend_mod, "_singleton", None)
