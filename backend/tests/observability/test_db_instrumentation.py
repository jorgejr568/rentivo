import pytest
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy import create_engine, text

from rentivo.observability import instrument_sqlalchemy


@pytest.fixture
def uninstrument_sqlalchemy():
    """Remove the global SQLAlchemy instrumentation patch after the test."""
    yield
    SQLAlchemyInstrumentor().uninstrument()


def test_instrument_noop_when_disabled():
    # No span_exporter fixture → tracing disabled. Must not raise and must not
    # attach any instrumentation.
    engine = create_engine("sqlite://")
    instrument_sqlalchemy(engine)  # no-op, no error
    engine.dispose()


def test_instrument_emits_a_span_per_query(span_exporter, uninstrument_sqlalchemy):
    engine = create_engine("sqlite://")
    instrument_sqlalchemy(engine)

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    spans = span_exporter.get_finished_spans()
    assert spans, "expected at least one DB span"
    # SQLAlchemy spans carry the db.system resource/attribute.
    assert any(s.attributes.get("db.system") == "sqlite" for s in spans)
    engine.dispose()


def test_suppress_tracing_silences_auto_instrumented_queries(span_exporter, uninstrument_sqlalchemy):
    from rentivo.observability import suppress_tracing

    engine = create_engine("sqlite://")
    instrument_sqlalchemy(engine)

    with suppress_tracing(), engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    assert span_exporter.get_finished_spans() == ()  # nothing traced inside

    with engine.connect() as conn:
        conn.execute(text("SELECT 2"))
    assert span_exporter.get_finished_spans(), "queries outside the block still trace"
    engine.dispose()


def test_suppress_tracing_noop_when_disabled():
    from rentivo.observability import suppress_tracing

    # No span_exporter → tracing off. Must just yield without error.
    with suppress_tracing():
        pass
