import pytest

from rentivo.settings import (
    Settings,  # noqa: E402 — top-level import ensures module is cached before monkeypatch activates
)


def test_dashboard_cache_backend_defaults_to_none(monkeypatch):
    for k in (
        "RENTIVO_DASHBOARD_CACHE_BACKEND",
        "RENTIVO_DASHBOARD_CACHE_TTL_SECONDS",
        "RENTIVO_DASHBOARD_CACHE_MAX_ENTRIES",
    ):
        monkeypatch.delenv(k, raising=False)

    s = Settings()
    assert s.dashboard_cache_backend == "none"
    assert s.dashboard_cache_ttl_seconds == 30
    assert s.dashboard_cache_max_entries == 1000


def test_dashboard_cache_backend_invalid_value(monkeypatch):
    monkeypatch.setenv("RENTIVO_DASHBOARD_CACHE_BACKEND", "memcached")

    with pytest.raises(ValueError, match="DASHBOARD_CACHE_BACKEND"):
        Settings()


def test_dashboard_cache_redis_requires_url(monkeypatch):
    monkeypatch.setenv("RENTIVO_DASHBOARD_CACHE_BACKEND", "redis")
    monkeypatch.setenv("RENTIVO_REDIS_URL", "")

    with pytest.raises(ValueError, match="RENTIVO_REDIS_URL"):
        Settings()


def test_dashboard_cache_ttl_must_be_positive(monkeypatch):
    monkeypatch.setenv("RENTIVO_DASHBOARD_CACHE_TTL_SECONDS", "0")

    with pytest.raises(ValueError, match="DASHBOARD_CACHE_TTL_SECONDS"):
        Settings()
