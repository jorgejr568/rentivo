from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from rentivo.observability.middleware import TracingMiddleware


def _app():
    async def ok(request):
        return PlainTextResponse("ok")

    async def boom(request):
        raise RuntimeError("kaboom")

    async def noise(request):
        return PlainTextResponse("noise")

    app = Starlette(
        routes=[
            Route("/ok", ok),
            Route("/boom", boom),
            Route("/health", noise),
            Route("/static/app.css", noise),
        ]
    )
    app.add_middleware(TracingMiddleware)
    return app


def test_request_produces_server_span(span_exporter):
    client = TestClient(_app())
    assert client.get("/ok").text == "ok"
    finished = span_exporter.get_finished_spans()
    assert finished[0].name == "HTTP GET"
    assert finished[0].attributes["http.request.method"] == "GET"
    assert finished[0].attributes["url.path"] == "/ok"
    assert finished[0].attributes["http.response.status_code"] == 200


def test_incoming_traceparent_continues_trace(span_exporter):
    client = TestClient(_app())
    # Well-formed W3C traceparent with a known trace id.
    trace_id = "0af7651916cd43dd8448eb211c80319c"
    headers = {"traceparent": f"00-{trace_id}-b7ad6b7169203331-01"}
    client.get("/ok", headers=headers)
    span_obj = span_exporter.get_finished_spans()[0]
    assert format(span_obj.context.trace_id, "032x") == trace_id


def test_error_marks_span(span_exporter):
    client = TestClient(_app(), raise_server_exceptions=False)
    client.get("/boom")
    span_obj = span_exporter.get_finished_spans()[0]
    assert span_obj.status.status_code.name == "ERROR"


def test_health_and_static_are_not_traced(span_exporter):
    client = TestClient(_app())
    assert client.get("/health").text == "noise"
    assert client.get("/static/app.css").text == "noise"
    assert span_exporter.get_finished_spans() == ()  # no spans for either
    # A real route still gets one.
    client.get("/ok")
    assert [s.name for s in span_exporter.get_finished_spans()] == ["HTTP GET"]


def test_disabled_passes_through():
    # No span_exporter fixture → tracing disabled. Must still serve requests.
    client = TestClient(_app())
    assert client.get("/ok").text == "ok"
