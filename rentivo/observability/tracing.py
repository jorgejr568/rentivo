"""OpenTelemetry tracing — the single module that imports opentelemetry.

opentelemetry is an OPTIONAL dependency (the ``otel`` extra). This module
guards every import; when the extra is absent OR ``RENTIVO_OTEL_ENABLED`` is
false, the module-global tracer stays ``None`` and every public helper
(``traced``, ``span``, ``set_attributes``, ``inject_context``,
``extract_context``) becomes a cheap no-op. Nothing else in the codebase
imports opentelemetry directly.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

from rentivo.settings import settings

try:  # opentelemetry is the optional `otel` extra
    from opentelemetry import trace as _trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.propagate import extract as _extract
    from opentelemetry.propagate import inject as _inject
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
    from opentelemetry.trace import Status, StatusCode

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - only when the otel extra is absent
    _OTEL_AVAILABLE = False

F = TypeVar("F", bound=Callable[..., Any])

_provider: Any = None
_tracer: Any = None


def _service_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("rentivo")
    except PackageNotFoundError:  # pragma: no cover - package is always installed
        return "0.0.0"


def _build_provider() -> Any:
    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": _service_version(),
            "deployment.environment": settings.environment,
        }
    )
    sampler = ParentBased(TraceIdRatioBased(settings.otel_sample_ratio))
    provider = TracerProvider(resource=resource, sampler=sampler)
    endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/traces"
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    return provider


def configure_tracing(*, provider: Any = None) -> None:
    """Install the tracer. Idempotent: a second call is a no-op while a tracer
    is live. Pass ``provider`` in tests to inject an in-memory exporter."""
    global _provider, _tracer
    if _tracer is not None:
        return
    if provider is None:
        if not (_OTEL_AVAILABLE and settings.otel_enabled):
            return
        provider = _build_provider()
    _provider = provider
    _tracer = provider.get_tracer("rentivo")


def tracing_enabled() -> bool:
    return _tracer is not None


def get_tracer() -> Any:
    return _tracer


def shutdown_tracing() -> None:
    global _provider, _tracer
    if _provider is not None:
        _provider.shutdown()
    _provider = None
    _tracer = None


def _reset_for_tests() -> None:
    shutdown_tracing()


def _apply_attributes(active_span: Any, attributes: dict[str, Any] | None) -> None:
    if attributes:
        for key, value in attributes.items():
            active_span.set_attribute(key, value)


def _record_error(active_span: Any, exc: Exception) -> None:
    active_span.record_exception(exc)
    active_span.set_status(Status(StatusCode.ERROR, str(exc)))


def traced(name: str | None = None, *, attributes: dict[str, Any] | None = None) -> Callable[[F], F]:
    """Wrap a sync or async function in a span. No-op while tracing is disabled.

    Span name defaults to the function's ``__name__``. ``attributes`` are
    static (evaluated once at decoration). For dynamic, non-PII attributes call
    :func:`set_attributes` inside the function body.
    """

    def decorator(fn: F) -> F:
        span_name = name or fn.__name__

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracer = _tracer
                if tracer is None:
                    return await fn(*args, **kwargs)
                with tracer.start_as_current_span(span_name) as active_span:
                    _apply_attributes(active_span, attributes)
                    try:
                        return await fn(*args, **kwargs)
                    except Exception as exc:
                        _record_error(active_span, exc)
                        raise

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = _tracer
            if tracer is None:
                return fn(*args, **kwargs)
            with tracer.start_as_current_span(span_name) as active_span:
                _apply_attributes(active_span, attributes)
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    _record_error(active_span, exc)
                    raise

        return wrapper  # type: ignore[return-value]

    return decorator


@contextmanager
def span(
    name: str,
    *,
    parent: Any = None,
    attributes: dict[str, Any] | None = None,
) -> Iterator[Any]:
    """Open a span for a code block. Yields the span, or ``None`` when disabled.

    ``parent`` is an opentelemetry ``Context`` (e.g. from :func:`extract_context`)
    used to re-parent a span across a process boundary; ``None`` continues the
    current in-process context.
    """
    tracer = _tracer
    if tracer is None:
        yield None
        return
    with tracer.start_as_current_span(name, context=parent) as active_span:
        _apply_attributes(active_span, attributes)
        try:
            yield active_span
        except Exception as exc:
            _record_error(active_span, exc)
            raise


def set_attributes(**attributes: Any) -> None:
    """Attach non-PII attributes to the currently-active span. No-op when disabled."""
    if _tracer is None:
        return
    current = _trace.get_current_span()
    for key, value in attributes.items():
        current.set_attribute(key, value)


def inject_context(carrier: dict) -> dict:
    """Write the current trace context into ``carrier`` (W3C ``traceparent``).
    Returns the same dict. No-op when disabled, so the carrier stays empty."""
    if _tracer is None:
        return carrier
    _inject(carrier)
    return carrier


def extract_context(carrier: dict) -> Any:
    """Read a trace context out of ``carrier`` for use as a ``span(parent=...)``.
    Returns ``None`` when disabled."""
    if _tracer is None:
        return None
    return _extract(carrier)
