from rentivo.jobs.temporal.config import TemporalConfig, config_from_settings
from rentivo.jobs.temporal.retry import (
    PERMANENT_ERROR_TYPE,
    is_permanent,
    should_give_up,
)


def test_permanent_error_type_constant():
    assert PERMANENT_ERROR_TYPE == "PermanentJobError"


def test_is_permanent():
    assert is_permanent("PermanentJobError") is True
    assert is_permanent("ValueError") is False
    assert is_permanent(None) is False


def test_should_give_up_on_permanent_regardless_of_attempts():
    assert should_give_up(attempt=1, max_attempts=5, permanent=True) is True


def test_should_give_up_when_attempts_exhausted():
    assert should_give_up(attempt=5, max_attempts=5, permanent=False) is True
    assert should_give_up(attempt=4, max_attempts=5, permanent=False) is False


def test_config_from_settings(monkeypatch):
    monkeypatch.setattr("rentivo.jobs.temporal.config.settings.temporal_host", "th:7233", raising=False)
    monkeypatch.setattr("rentivo.jobs.temporal.config.settings.temporal_namespace", "ns", raising=False)
    monkeypatch.setattr("rentivo.jobs.temporal.config.settings.temporal_task_queue", "q", raising=False)
    monkeypatch.setattr("rentivo.jobs.temporal.config.settings.temporal_tls", True, raising=False)
    monkeypatch.setattr(
        "rentivo.jobs.temporal.config.settings.temporal_activity_start_to_close_timeout_seconds",
        42,
        raising=False,
    )
    cfg = config_from_settings()
    assert cfg == TemporalConfig(host="th:7233", namespace="ns", task_queue="q", tls=True, activity_timeout_seconds=42)
