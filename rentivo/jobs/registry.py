from __future__ import annotations

from typing import Callable

HandlerFn = Callable[[dict], None]
HandlerOnFailFn = Callable[[dict], None]

_REGISTRY: dict[str, HandlerFn] = {}
_FAIL_HOOKS: dict[str, HandlerOnFailFn] = {}


def register(job_type: str) -> Callable[[HandlerFn], HandlerFn]:
    def deco(fn: HandlerFn) -> HandlerFn:
        if job_type in _REGISTRY:
            raise ValueError(f"Handler already registered for job_type {job_type!r}")
        _REGISTRY[job_type] = fn
        return fn

    return deco


def get(job_type: str) -> HandlerFn | None:
    return _REGISTRY.get(job_type)


def register_on_fail(job_type: str) -> Callable[[HandlerOnFailFn], HandlerOnFailFn]:
    def deco(fn: HandlerOnFailFn) -> HandlerOnFailFn:
        if job_type in _FAIL_HOOKS:
            raise ValueError(f"Fail hook already registered for job_type {job_type!r}")
        _FAIL_HOOKS[job_type] = fn
        return fn

    return deco


def get_fail_hook(job_type: str) -> HandlerOnFailFn | None:
    return _FAIL_HOOKS.get(job_type)
