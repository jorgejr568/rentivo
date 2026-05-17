"""Shared fixtures for encryption tests."""

from __future__ import annotations

import pytest


def _reset_and_close() -> None:
    """Close any cache resources held by the cached backend, then drop it."""
    from rentivo.encryption import factory as factory_module
    from rentivo.encryption.caching import CachingEncryptionBackend

    backend = factory_module._backend
    if isinstance(backend, CachingEncryptionBackend):
        backend.cache.close()
    factory_module._reset_for_tests()


@pytest.fixture(autouse=True)
def _reset_encryption_cache():
    """Clear the module-level backend cache between tests so monkeypatched
    settings actually take effect on each call to ``get_encryption()``, and
    ensure any background threads from a previous test are joined."""
    _reset_and_close()
    yield
    _reset_and_close()
