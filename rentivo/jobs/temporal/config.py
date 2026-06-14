from __future__ import annotations

from dataclasses import dataclass

from rentivo.settings import settings


@dataclass(frozen=True)
class TemporalConfig:
    host: str
    namespace: str
    task_queue: str
    tls: bool
    activity_timeout_seconds: int


def config_from_settings() -> TemporalConfig:
    return TemporalConfig(
        host=settings.temporal_host,
        namespace=settings.temporal_namespace,
        task_queue=settings.temporal_task_queue,
        tls=settings.temporal_tls,
        activity_timeout_seconds=settings.temporal_activity_start_to_close_timeout_seconds,
    )
