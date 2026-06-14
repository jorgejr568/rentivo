from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from rentivo.jobs.base import Job
from rentivo.observability import span, tracing
from rentivo.services.job_service import JobService


class _FakeJobRepo:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, job_type, payload, run_after, max_attempts):
        self.enqueued.append((job_type, payload))
        return Job(id=1, ulid="01J", job_type=job_type, payload=payload, attempts=0, max_attempts=max_attempts)


class _NullAudit:
    def safe_log(self, **kwargs):
        return None


def test_enqueue_without_tracing_leaves_payload_untouched():
    tracing._reset_for_tests()
    repo = _FakeJobRepo()
    JobService(repo, _NullAudit()).enqueue("pdf.render", {"bill_id": 7})
    assert repo.enqueued[0][1] == {"bill_id": 7}
    assert "_otel" not in repo.enqueued[0][1]


def test_enqueue_injects_otel_carrier_when_tracing_on():
    tracing._reset_for_tests()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
    tracing.configure_tracing(provider=provider)
    try:
        repo = _FakeJobRepo()
        with span("request"):
            JobService(repo, _NullAudit()).enqueue("pdf.render", {"bill_id": 7})
        stored = repo.enqueued[0][1]
        assert stored["bill_id"] == 7
        assert "traceparent" in stored["_otel"]
    finally:
        tracing._reset_for_tests()
