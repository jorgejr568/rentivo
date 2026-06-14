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
