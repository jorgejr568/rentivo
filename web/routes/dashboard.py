from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from rentivo.models.dashboard import DashboardScope
from web.analytics import analytics_hash, push_event
from web.deps import get_dashboard_service, render

router = APIRouter()


@router.get("/dashboard")
async def dashboard(request: Request):
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401)
    service = get_dashboard_service(request)
    metrics = service.get_metrics(DashboardScope(kind="user", id=user_id))
    push_event(
        request,
        {
            "event": "rentivo_dashboard_viewed",
            "scope_kind": "user",
            "scope_id_hash": analytics_hash(str(user_id)),
        },
    )
    return render(
        request,
        "dashboard/index.html",
        {"metrics": metrics, "page_template": "dashboard"},
    )
