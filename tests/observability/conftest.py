import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from rentivo.observability import tracing


@pytest.fixture(autouse=True)
def reset_tracing():
    """Guarantee a clean global tracer before and after every test."""
    tracing._reset_for_tests()
    yield
    tracing._reset_for_tests()


@pytest.fixture
def span_exporter():
    """Configure tracing with an in-memory exporter and return it."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracing.configure_tracing(provider=provider)
    return exporter
