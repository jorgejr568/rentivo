"""Factory isolation for cache tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_cache_factory():
    """Close and drop the module-level cache between tests so monkeypatched
    settings take effect and background threads from a prior test are joined."""
    from rentivo.cache import factory as factory_module

    factory_module._reset_for_tests()
    yield
    factory_module._reset_for_tests()


@pytest.fixture()
def value() -> dict:
    return {"year": 2026, "expected": 460400, "nested": {"a": [1, 2, 3]}}
