"""Shared fixtures for encryption tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_encryption_cache():
    """Clear the module-level backend cache between tests so monkeypatched
    settings actually take effect on each call to ``get_encryption()``.
    """
    from rentivo.encryption.factory import _reset_for_tests

    _reset_for_tests()
    yield
    _reset_for_tests()
