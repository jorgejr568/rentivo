"""Per-request context objects for the web app.

WebActor collapses the (actor_id, actor_username, source) trio that every
web call site to AuditService / JobService used to derive by hand. Built
once per request by AuthMiddleware, attached to request.state.actor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class WebActor:
    user_id: int | None
    email: str
    source: str = "web"


ANON_ACTOR: WebActor = WebActor(user_id=None, email="", source="web")


def actor_from_session(session: Mapping) -> WebActor:
    user_id = session.get("user_id")
    if user_id is None:
        return ANON_ACTOR
    return WebActor(user_id=int(user_id), email=session.get("email", ""))
