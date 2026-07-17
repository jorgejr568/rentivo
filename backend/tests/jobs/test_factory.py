from unittest.mock import MagicMock

import pytest

from rentivo.jobs.backend import DatabaseJobBackend
from rentivo.jobs.factory import get_job_backend


def test_factory_returns_database_backend_by_default(monkeypatch):
    monkeypatch.setattr("rentivo.jobs.factory.settings.job_backend", "database", raising=False)
    backend = get_job_backend(MagicMock())
    assert isinstance(backend, DatabaseJobBackend)


def test_factory_rejects_unknown_backend(monkeypatch):
    monkeypatch.setattr("rentivo.jobs.factory.settings.job_backend", "bogus", raising=False)
    with pytest.raises(ValueError, match="Unsupported job backend"):
        get_job_backend(MagicMock())


def test_factory_returns_temporal_backend(monkeypatch):
    monkeypatch.setattr("rentivo.jobs.factory.settings.job_backend", "temporal", raising=False)
    sentinel = object()
    monkeypatch.setattr("rentivo.jobs.temporal.backend.build_temporal_backend", lambda: sentinel)
    assert get_job_backend(MagicMock()) is sentinel
