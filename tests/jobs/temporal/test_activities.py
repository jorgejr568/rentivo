import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from rentivo.jobs import registry
from rentivo.jobs.base import PermanentJobError
from rentivo.jobs.temporal import activities
from rentivo.models.audit_log import AuditEventType


def test_run_registered_handler_invokes_handler(clean_registry):
    calls = []
    registry.register("email.send")(lambda p: calls.append(p))
    activities.run_registered_handler("email.send", {"to": "x"})
    assert calls == [{"to": "x"}]


def test_run_registered_handler_missing_handler_is_permanent(clean_registry):
    with pytest.raises(ApplicationError) as exc:
        activities.run_registered_handler("nope", {})
    assert exc.value.type == "PermanentJobError"
    assert exc.value.non_retryable is True


def test_run_registered_handler_maps_permanent_job_error(clean_registry):
    def boom(_p):
        raise PermanentJobError("bad input")

    registry.register("email.send")(boom)
    with pytest.raises(ApplicationError) as exc:
        activities.run_registered_handler("email.send", {})
    assert exc.value.type == "PermanentJobError"
    assert exc.value.non_retryable is True


def test_run_registered_handler_lets_transient_error_propagate(clean_registry):
    def boom(_p):
        raise RuntimeError("network")

    registry.register("email.send")(boom)
    with pytest.raises(RuntimeError, match="network"):
        activities.run_registered_handler("email.send", {})


def test_email_send_activity_runs_through_env(clean_registry):
    calls = []
    registry.register("email.send")(lambda p: calls.append(p))
    env = ActivityEnvironment()
    env.run(activities.email_send_activity, {"to": "y"})
    assert calls == [{"to": "y"}]


def test_other_activities_run_through_env(clean_registry):
    calls = {}
    registry.register("communication.send")(lambda p: calls.setdefault("communication.send", p))
    registry.register("pdf.render")(lambda p: calls.setdefault("pdf.render", p))
    registry.register("recibo.render")(lambda p: calls.setdefault("recibo.render", p))
    registry.register("s3.delete")(lambda p: calls.setdefault("s3.delete", p))
    env = ActivityEnvironment()
    env.run(activities.communication_send_activity, {"a": 1})
    env.run(activities.pdf_render_activity, {"b": 2})
    env.run(activities.recibo_render_activity, {"d": 4})
    env.run(activities.s3_delete_activity, {"c": 3})
    assert calls == {
        "communication.send": {"a": 1},
        "pdf.render": {"b": 2},
        "recibo.render": {"d": 4},
        "s3.delete": {"c": 3},
    }


def test_open_audit_returns_audit_and_close(monkeypatch):
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import StaticPool

    import rentivo.db as db_mod
    from rentivo.services.audit_service import AuditService
    from tests.conftest import SCHEMA_DDL

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with eng.connect() as c:
        for stmt in SCHEMA_DDL.strip().split(";"):
            if stmt.strip():
                c.execute(text(stmt))
        c.commit()

    monkeypatch.setattr(db_mod, "get_engine", lambda: eng)

    audit, close = activities._open_audit()
    assert isinstance(audit, AuditService)
    # A real safe_log against the schema-backed connection must not raise.
    audit.safe_log(
        event_type="job.succeeded",
        source="worker",
        actor_id=None,
        actor_username="",
        entity_type="job",
        entity_uuid="01OPEN",
        previous_state=None,
        new_state={"ok": True},
    )
    close()
    eng.dispose()


def test_finalize_job_activity_runs_through_env(monkeypatch):
    logged = []
    monkeypatch.setattr(activities, "_open_audit", lambda: (_FakeAudit(logged), _noop_close))
    env = ActivityEnvironment()
    env.run(
        activities.finalize_job_activity,
        {"kind": "succeeded", "job_type": "email.send", "ulid": "01N", "attempts": 1},
    )
    assert logged[0]["event_type"] == AuditEventType.JOB_SUCCEEDED


def test_finalize_job_succeeded_writes_audit(monkeypatch):
    logged = []
    monkeypatch.setattr(activities, "_open_audit", lambda: (_FakeAudit(logged), _noop_close))
    activities.finalize_job(
        {"kind": "succeeded", "job_type": "email.send", "ulid": "01J", "attempts": 1, "payload": {}}
    )
    assert logged[0]["event_type"] == AuditEventType.JOB_SUCCEEDED
    assert logged[0]["new_state"] == {"job_type": "email.send", "ulid": "01J", "attempts": 1}


def test_finalize_job_failed_runs_fail_hook(clean_registry, monkeypatch):
    logged = []
    monkeypatch.setattr(activities, "_open_audit", lambda: (_FakeAudit(logged), _noop_close))
    hook_calls = []
    registry.register_on_fail("pdf.render")(lambda p: hook_calls.append(p))

    activities.finalize_job(
        {
            "kind": "failed",
            "job_type": "pdf.render",
            "ulid": "01K",
            "attempts": 5,
            "error": "boom",
            "payload": {"bill_id": 3},
        }
    )
    assert logged[0]["event_type"] == AuditEventType.JOB_FAILED
    assert logged[0]["new_state"]["error"] == "boom"
    assert hook_calls == [{"bill_id": 3}]


def test_finalize_job_failed_swallows_fail_hook_error(clean_registry, monkeypatch):
    monkeypatch.setattr(activities, "_open_audit", lambda: (_FakeAudit([]), _noop_close))

    def bad_hook(_p):
        raise RuntimeError("hook blew up")

    registry.register_on_fail("pdf.render")(bad_hook)
    # Must not raise.
    activities.finalize_job(
        {"kind": "failed", "job_type": "pdf.render", "ulid": "01K", "attempts": 5, "error": "x", "payload": {}}
    )


def test_finalize_job_retry_includes_next_run_after(monkeypatch):
    logged = []
    monkeypatch.setattr(activities, "_open_audit", lambda: (_FakeAudit(logged), _noop_close))
    activities.finalize_job(
        {
            "kind": "retry",
            "job_type": "email.send",
            "ulid": "01M",
            "attempts": 2,
            "error": "transient",
            "next_run_after": "2026-01-01T00:05:00+00:00",
            "payload": {},
        }
    )
    assert logged[0]["event_type"] == AuditEventType.JOB_RETRY_SCHEDULED
    assert logged[0]["new_state"]["next_run_after"] == "2026-01-01T00:05:00+00:00"


def _noop_close():
    pass


class _FakeAudit:
    def __init__(self, sink):
        self.sink = sink

    def safe_log(self, **kwargs):
        self.sink.append(kwargs)
        return None
