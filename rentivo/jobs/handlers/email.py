from __future__ import annotations

from jinja2 import TemplateError, TemplateNotFound

from rentivo.email.factory import get_email_backend
from rentivo.jobs.base import PermanentJobError
from rentivo.jobs.registry import register
from rentivo.services.email_service import EmailService
from rentivo.settings import settings


@register("email.send")
def handle_email_send(payload: dict) -> None:
    backend = get_email_backend()
    service = EmailService(
        backend,
        from_address=settings.ses_from_email or "noreply@localhost",
    )
    event = payload["event"]
    to_email = payload["to_email"]
    ctx = payload.get("ctx", {})
    try:
        service.send(to_email, event, ctx)
    except KeyError as exc:
        raise PermanentJobError(f"unknown email event: {exc}") from exc
    except (TemplateNotFound, TemplateError) as exc:
        raise PermanentJobError(f"template error: {exc}") from exc
