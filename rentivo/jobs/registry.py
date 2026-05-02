from __future__ import annotations

from typing import Callable

HandlerFn = Callable[[dict], None]

_REGISTRY: dict[str, HandlerFn] = {}


def register(job_type: str) -> Callable[[HandlerFn], HandlerFn]:
    def deco(fn: HandlerFn) -> HandlerFn:
        if job_type in _REGISTRY:
            raise ValueError(f"Handler already registered for job_type {job_type!r}")
        _REGISTRY[job_type] = fn
        return fn

    return deco


def get(job_type: str) -> HandlerFn | None:
    return _REGISTRY.get(job_type)
