import pytest

from rentivo.jobs import registry
from tests.observability.conftest import reset_tracing, span_exporter  # noqa: F401


@pytest.fixture
def clean_registry():
    """Snapshot and restore the global handler registry around a test."""
    saved = dict(registry._REGISTRY)
    saved_hooks = dict(registry._FAIL_HOOKS)
    registry._REGISTRY.clear()
    registry._FAIL_HOOKS.clear()
    try:
        yield registry
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(saved)
        registry._FAIL_HOOKS.clear()
        registry._FAIL_HOOKS.update(saved_hooks)
