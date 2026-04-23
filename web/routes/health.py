"""Liveness probe endpoint.

Returns 200 unconditionally so container orchestrators (Docker, Kubernetes,
load balancers) can confirm the web process is up. Successful probes are
suppressed from request logs by ``RequestContextMiddleware``.
"""

from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})
