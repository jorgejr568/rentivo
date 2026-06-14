import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from rentivo.observability import tracing


@pytest.fixture
def web_span_exporter():
    tracing._reset_for_tests()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracing.configure_tracing(provider=provider)
    yield exporter
    tracing._reset_for_tests()


def test_request_emits_server_span(client, web_span_exporter):
    # /login is public and traced (/health and /static are deliberately excluded).
    resp = client.get("/login")
    assert resp.status_code == 200
    names = [s.name for s in web_span_exporter.get_finished_spans()]
    assert "HTTP GET" in names


def test_health_is_not_traced(client, web_span_exporter):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert web_span_exporter.get_finished_spans() == ()
