"""Google Tag Manager analytics helpers.

This module is a no-op when ``RENTIVO_GTM_CONTAINER_ID`` is empty, making
GTM integration entirely opt-in.

Pattern
-------
- ``build_page_context`` produces the initial ``dataLayer.push({...})`` payload
  rendered inline in ``base.html`` before the GTM loader fires.
- ``push_event`` queues one-shot business events in the session (flash-style)
  so POST handlers can emit outcome events that render on the post-redirect
  destination page.
- ``pop_events`` drains the queue — called once per rendered page from
  ``web.deps.render``.

Privacy
-------
Identifiers are always hashed with HMAC-SHA256 keyed by the app secret key.
Usernames, emails, PIX data, and other PII must never be placed in a
dataLayer payload. See ``docs/superpowers/specs/2026-04-19-gtm-analytics-design.md``.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from starlette.requests import Request

from rentivo.settings import settings

HASH_LEN = 16
SESSION_KEY = "_analytics_events"


def analytics_hash(value: Any) -> str | None:
    """Return HMAC-SHA256 of ``value`` (first 16 hex chars), keyed by the app secret.

    Returns ``None`` when ``value`` is ``None`` or an empty string.
    """
    if value is None or value == "":
        return None
    key = settings.secret_key.encode()
    return hmac.new(key, str(value).encode(), hashlib.sha256).hexdigest()[:HASH_LEN]


PAGE_TYPE_MAP: dict[str, str] = {
    "billing/list": "list",
    "billing/detail": "detail",
    "billing/create": "form",
    "billing/edit": "form",
    "bill/generate": "form",
    "bill/detail": "detail",
    "bill/edit": "form",
    "organization/list": "list",
    "organization/detail": "detail",
    "organization/create": "form",
    "organization/edit": "form",
    "invite/list": "list",
    "security/index": "dashboard",
    "security/totp_setup": "form",
    "security/recovery_codes": "detail",
    "theme/edit": "form",
    "login": "auth",
    "signup": "auth",
    "mfa_verify": "auth",
    "landing": "landing",
    "404": "error",
}


def _infer_page_type(template_stem: str) -> str:
    if template_stem in PAGE_TYPE_MAP:
        return PAGE_TYPE_MAP[template_stem]
    if template_stem.endswith(("/create", "/edit", "/generate")):
        return "form"
    if template_stem.endswith("/list"):
        return "list"
    if template_stem.endswith("/detail"):
        return "detail"
    return "other"


def build_page_context(request: Request, template_name: str, ctx: dict) -> dict | None:
    """Build the initial ``dataLayer.push({...})`` payload. Returns ``None`` if GTM disabled."""
    if not settings.gtm_container_id:
        return None
    stem = template_name.removesuffix(".html")
    section = stem.split("/")[0] if "/" in stem else "root"
    user_id = request.session.get("user_id")
    return {
        "event": "page_context",
        "page_type": _infer_page_type(stem),
        "page_section": section,
        "page_template": stem,
        "user_status": "authenticated" if user_id else "anonymous",
        "user_id_hash": analytics_hash(user_id),
        "locale": "pt-BR",
        "environment": settings.environment,
        "app_version": ctx.get("asset_version", ""),
        "request_id": getattr(request.state, "request_id", None),
    }


def push_event(request: Request, event: dict) -> None:
    """Queue a one-shot dataLayer event for the next rendered page (flash-style).

    No-op when GTM is disabled, so call sites don't need to check the flag.
    """
    if not settings.gtm_container_id:
        return
    events = request.session.setdefault(SESSION_KEY, [])
    events.append(event)


def pop_events(request: Request) -> list[dict]:
    """Drain queued one-shot events. Called by ``render()`` once per page."""
    return request.session.pop(SESSION_KEY, [])
