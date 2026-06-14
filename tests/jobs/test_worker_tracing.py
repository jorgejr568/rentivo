from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from rentivo.jobs import registry
from rentivo.jobs.base import Job
from rentivo.observability import inject_context, span, tracing


class _Repo:
    def claim_batch(self, *a):
        return []

    def mark_succeeded(self, job_id):
        pass


class _NullAudit:
    def safe_log(self, **kwargs):
        return None


def _make_worker():
    from rentivo.jobs.worker import Worker

    return Worker(_Repo(), _NullAudit())


def test_job_span_is_child_of_originating_request():
    tracing._reset_for_tests()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracing.configure_tracing(provider=provider)
    registry.register("test.trace.job")(lambda payload: None)
    try:
        carrier: dict = {}
        with span("request"):
            inject_context(carrier)
        job = Job(
            id=1,
            ulid="01J",
            job_type="test.trace.job",
            payload={"_otel": carrier},
            attempts=1,
            max_attempts=3,
        )
        _make_worker()._run_one(job)
        finished = {s.name: s for s in exporter.get_finished_spans()}
        assert finished["job test.trace.job"].parent.span_id == finished["request"].context.span_id
    finally:
        registry._REGISTRY.pop("test.trace.job", None)
        tracing._reset_for_tests()
