from rentivo.observability import extract_context, inject_context, span


def test_inject_noop_when_disabled():
    carrier: dict = {}
    assert inject_context(carrier) is carrier
    assert carrier == {}


def test_extract_noop_when_disabled():
    assert extract_context({"traceparent": "x"}) is None


def test_inject_populates_traceparent(span_exporter):
    carrier: dict = {}
    with span("producer"):
        inject_context(carrier)
    assert "traceparent" in carrier


def test_roundtrip_reparents_across_boundary(span_exporter):
    carrier: dict = {}
    with span("producer"):
        inject_context(carrier)

    parent = extract_context(carrier)
    with span("consumer", parent=parent):
        pass

    finished = {s.name: s for s in span_exporter.get_finished_spans()}
    producer = finished["producer"]
    consumer = finished["consumer"]
    # Same trace, and consumer is a child of producer despite separate scopes.
    assert consumer.context.trace_id == producer.context.trace_id
    assert consumer.parent.span_id == producer.context.span_id
