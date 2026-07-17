"""Optional OpenTelemetry tracing. Import these helpers anywhere; they no-op
when tracing is disabled or the ``otel`` extra is not installed."""

from rentivo.observability.tracing import (
    configure_tracing,
    current_trace_ids,
    extract_context,
    get_tracer,
    inject_context,
    instrument_sqlalchemy,
    set_attributes,
    shutdown_tracing,
    span,
    suppress_tracing,
    traced,
    tracing_enabled,
)

__all__ = [
    "configure_tracing",
    "current_trace_ids",
    "extract_context",
    "get_tracer",
    "inject_context",
    "instrument_sqlalchemy",
    "set_attributes",
    "shutdown_tracing",
    "span",
    "suppress_tracing",
    "traced",
    "tracing_enabled",
]
