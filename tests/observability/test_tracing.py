import pytest

from rentivo.observability import current_trace_ids, set_attributes, span, traced, tracing


def test_disabled_by_default():
    assert tracing.tracing_enabled() is False
    assert tracing.get_tracer() is None


def test_configure_with_injected_provider_enables(span_exporter):
    assert tracing.tracing_enabled() is True
    assert tracing.get_tracer() is not None


def test_configure_is_idempotent(span_exporter):
    first = tracing.get_tracer()
    # A second call with no provider must NOT replace the live tracer.
    tracing.configure_tracing()
    assert tracing.get_tracer() is first


def test_configure_from_settings_builds_otlp_provider(monkeypatch):
    monkeypatch.setattr(tracing.settings, "otel_enabled", True)
    monkeypatch.setattr(tracing.settings, "otel_exporter_otlp_endpoint", "http://localhost:4318")
    monkeypatch.setattr(tracing.settings, "otel_sample_ratio", 1.0)
    tracing.configure_tracing()
    assert tracing.tracing_enabled() is True


def test_configure_noop_when_settings_disabled(monkeypatch):
    monkeypatch.setattr(tracing.settings, "otel_enabled", False)
    tracing.configure_tracing()
    assert tracing.tracing_enabled() is False


def test_shutdown_resets(span_exporter):
    assert tracing.tracing_enabled() is True
    tracing.shutdown_tracing()
    assert tracing.tracing_enabled() is False


def _names(exporter):
    return [s.name for s in exporter.get_finished_spans()]


def test_traced_noop_when_disabled():
    calls = []

    @traced("thing")
    def f(x):
        calls.append(x)
        return x * 2

    assert f(3) == 6
    assert calls == [3]


def test_traced_emits_named_span(span_exporter):
    @traced("compute.thing")
    def f():
        return 42

    assert f() == 42
    assert _names(span_exporter) == ["compute.thing"]


def test_traced_defaults_name_to_qualname(span_exporter):
    @traced()
    def widget():
        return 1

    widget()
    assert _names(span_exporter) == ["widget"]


def test_traced_sets_static_attributes(span_exporter):
    @traced("op", attributes={"backend": "kms"})
    def f():
        return None

    f()
    finished = span_exporter.get_finished_spans()
    assert finished[0].attributes["backend"] == "kms"


def test_traced_records_and_reraises_error(span_exporter):
    @traced("boom")
    def f():
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        f()
    finished = span_exporter.get_finished_spans()
    assert finished[0].status.status_code.name == "ERROR"
    assert any(e.name == "exception" for e in finished[0].events)


@pytest.mark.asyncio
async def test_traced_async_noop_when_disabled():
    @traced("async.disabled")
    async def f(x):
        return x * 2

    # No span_exporter fixture → tracing disabled. The async wrapper must take
    # its tracer-is-None fast path and just await the wrapped coroutine.
    assert await f(4) == 8


@pytest.mark.asyncio
async def test_traced_supports_async(span_exporter):
    @traced("async.op")
    async def f():
        return "ok"

    assert await f() == "ok"
    assert _names(span_exporter) == ["async.op"]


@pytest.mark.asyncio
async def test_traced_async_records_error(span_exporter):
    @traced("async.boom")
    async def f():
        raise RuntimeError("async fail")

    with pytest.raises(RuntimeError, match="async fail"):
        await f()
    assert span_exporter.get_finished_spans()[0].status.status_code.name == "ERROR"


def test_span_contextmanager_nests(span_exporter):
    with span("outer"):
        with span("inner"):
            pass
    finished = span_exporter.get_finished_spans()
    by_name = {s.name: s for s in finished}
    assert by_name["inner"].parent.span_id == by_name["outer"].context.span_id


def test_span_noop_when_disabled():
    with span("x") as s:
        assert s is None


def test_span_records_error(span_exporter):
    with pytest.raises(ValueError):
        with span("ctx.boom"):
            raise ValueError("x")
    assert span_exporter.get_finished_spans()[0].status.status_code.name == "ERROR"


def test_set_attributes_on_current_span(span_exporter):
    with span("op"):
        set_attributes(count=5)
    assert span_exporter.get_finished_spans()[0].attributes["count"] == 5


def test_set_attributes_noop_when_disabled():
    set_attributes(count=5)  # must not raise


def test_current_trace_ids_none_when_disabled():
    assert current_trace_ids() is None


def test_current_trace_ids_none_when_no_active_span(span_exporter):
    # Tracing on, but not inside any span.
    assert current_trace_ids() is None


def test_current_trace_ids_inside_span(span_exporter):
    with span("op"):
        ids = current_trace_ids()
    assert ids is not None
    trace_id, span_id = ids
    assert len(trace_id) == 32
    assert len(span_id) == 16
