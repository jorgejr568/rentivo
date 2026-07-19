from datetime import datetime
from unittest.mock import MagicMock

from rentivo.context import ANON_ACTOR, Actor
from rentivo.jobs.base import Job
from rentivo.services.job_service import JobService


def _make_job(**overrides) -> Job:
    defaults = dict(
        id=42,
        ulid="01HXYZ",
        job_type="email.send",
        payload={"event": "welcome"},
        attempts=0,
        max_attempts=5,
    )
    defaults.update(overrides)
    return Job(**defaults)


def test_enqueue_calls_repo_and_returns_job():
    repo = MagicMock()
    repo.enqueue.return_value = _make_job()
    audit = MagicMock()
    svc = JobService(repo, audit)

    result = svc.enqueue("email.send", {"event": "welcome"})

    assert result.id == 42
    repo.enqueue.assert_called_once_with("email.send", {"event": "welcome"}, None, 5)


def test_enqueue_emits_job_enqueued_audit_event():
    from rentivo.models.audit_log import AuditEventType

    repo = MagicMock()
    repo.enqueue.return_value = _make_job()
    audit = MagicMock()
    svc = JobService(repo, audit)

    svc.enqueue("email.send", {"event": "welcome"}, source="web", actor_id=7, actor_username="a@x")

    audit.safe_log.assert_called_once()
    kwargs = audit.safe_log.call_args.kwargs
    assert kwargs["event_type"] == AuditEventType.JOB_ENQUEUED
    assert kwargs["source"] == "web"
    assert kwargs["actor_id"] == 7
    assert kwargs["actor_username"] == "a@x"
    new_state = kwargs["new_state"]
    assert new_state["job_type"] == "email.send"
    assert new_state["ulid"] == "01HXYZ"
    assert new_state["attempts"] == 0
    # new_state must run through serialize_job_payload — sensitive keys absent
    assert "ctx" not in new_state


def test_enqueue_passes_run_after_and_max_attempts_through():
    repo = MagicMock()
    repo.enqueue.return_value = _make_job(max_attempts=3)
    audit = MagicMock()
    svc = JobService(repo, audit)

    when = datetime(2030, 1, 1, 12, 0, 0)
    svc.enqueue("email.send", {"event": "welcome"}, run_after=when, max_attempts=3)

    repo.enqueue.assert_called_once_with("email.send", {"event": "welcome"}, when, 3)


def test_enqueue_default_source_is_empty_string():
    repo = MagicMock()
    repo.enqueue.return_value = _make_job()
    audit = MagicMock()
    svc = JobService(repo, audit)

    svc.enqueue("email.send", {"event": "welcome"})

    assert audit.safe_log.call_args.kwargs["source"] == ""


class TestEnqueueFor:
    """Tests for enqueue_for's actor-unpacking convenience wrapper."""

    def test_enqueue_for_unpacks_actor(self):
        repo = MagicMock()
        repo.enqueue.return_value = _make_job()
        audit = MagicMock()
        svc = JobService(repo, audit)

        actor = Actor(user_id=7, email="a@x.z", source="web")
        result = svc.enqueue_for(actor, "email.send", {"event": "welcome"})

        assert result.id == 42
        repo.enqueue.assert_called_once_with("email.send", {"event": "welcome"}, None, 5)
        kwargs = audit.safe_log.call_args.kwargs
        assert kwargs["source"] == "web"
        assert kwargs["actor_id"] == 7
        assert kwargs["actor_username"] == "a@x.z"

    def test_enqueue_for_anon_actor(self):
        repo = MagicMock()
        repo.enqueue.return_value = _make_job()
        audit = MagicMock()
        svc = JobService(repo, audit)

        svc.enqueue_for(ANON_ACTOR, "email.send", {"event": "welcome"})

        kwargs = audit.safe_log.call_args.kwargs
        assert kwargs["source"] == "anonymous"
        assert kwargs["actor_id"] is None
        assert kwargs["actor_username"] == ""

    def test_enqueue_for_passes_run_after_and_max_attempts(self):
        repo = MagicMock()
        repo.enqueue.return_value = _make_job(max_attempts=3)
        audit = MagicMock()
        svc = JobService(repo, audit)

        when = datetime(2030, 1, 1, 12, 0, 0)
        svc.enqueue_for(
            Actor(user_id=1, email="x@y.z", source="web"),
            "email.send",
            {"event": "welcome"},
            run_after=when,
            max_attempts=3,
        )

        repo.enqueue.assert_called_once_with("email.send", {"event": "welcome"}, when, 3)
