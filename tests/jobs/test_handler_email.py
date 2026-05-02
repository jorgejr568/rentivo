from unittest.mock import MagicMock, patch

import pytest

from rentivo.jobs.base import PermanentJobError


def test_handler_dispatches_event_to_send_with_full_ctx():
    with (
        patch("rentivo.jobs.handlers.email.EmailService") as svc_cls,
        patch("rentivo.jobs.handlers.email.get_email_backend"),
    ):
        instance = MagicMock()
        svc_cls.return_value = instance
        from rentivo.jobs.handlers.email import handle_email_send

        handle_email_send(
            {
                "event": "welcome",
                "to_email": "alice@example.com",
                "ctx": {"email": "alice@example.com", "pix_setup_url": "http://x/pix"},
            }
        )

        instance.send.assert_called_once_with(
            "alice@example.com",
            "welcome",
            {"email": "alice@example.com", "pix_setup_url": "http://x/pix"},
        )


def test_handler_routes_password_reset_through_send_too():
    """password_reset has no special handling — it goes through send like every other event."""
    with (
        patch("rentivo.jobs.handlers.email.EmailService") as svc_cls,
        patch("rentivo.jobs.handlers.email.get_email_backend"),
    ):
        instance = MagicMock()
        svc_cls.return_value = instance
        from rentivo.jobs.handlers.email import handle_email_send

        handle_email_send(
            {
                "event": "password_reset",
                "to_email": "alice@example.com",
                "ctx": {"email": "alice@example.com", "reset_url": "http://x/r"},
            }
        )

        instance.send.assert_called_once_with(
            "alice@example.com",
            "password_reset",
            {"email": "alice@example.com", "reset_url": "http://x/r"},
        )


def test_handler_uses_default_empty_ctx_when_missing():
    with (
        patch("rentivo.jobs.handlers.email.EmailService") as svc_cls,
        patch("rentivo.jobs.handlers.email.get_email_backend"),
    ):
        instance = MagicMock()
        svc_cls.return_value = instance
        from rentivo.jobs.handlers.email import handle_email_send

        handle_email_send({"event": "welcome", "to_email": "alice@example.com"})

        instance.send.assert_called_once_with("alice@example.com", "welcome", {})


def test_handler_raises_permanent_error_for_unknown_event():
    with (
        patch("rentivo.jobs.handlers.email.EmailService") as svc_cls,
        patch("rentivo.jobs.handlers.email.get_email_backend"),
    ):
        instance = MagicMock()
        instance.send.side_effect = KeyError("nope.event")
        svc_cls.return_value = instance
        from rentivo.jobs.handlers.email import handle_email_send

        with pytest.raises(PermanentJobError, match="nope.event"):
            handle_email_send(
                {
                    "event": "nope.event",
                    "to_email": "alice@example.com",
                    "ctx": {},
                }
            )


def test_handler_raises_permanent_error_for_template_not_found():
    from jinja2 import TemplateNotFound

    with (
        patch("rentivo.jobs.handlers.email.EmailService") as svc_cls,
        patch("rentivo.jobs.handlers.email.get_email_backend"),
    ):
        instance = MagicMock()
        instance.send.side_effect = TemplateNotFound("welcome.html")
        svc_cls.return_value = instance
        from rentivo.jobs.handlers.email import handle_email_send

        with pytest.raises(PermanentJobError, match="welcome.html"):
            handle_email_send(
                {
                    "event": "welcome",
                    "to_email": "alice@example.com",
                    "ctx": {},
                }
            )


def test_handler_propagates_other_exceptions_for_retry():
    with (
        patch("rentivo.jobs.handlers.email.EmailService") as svc_cls,
        patch("rentivo.jobs.handlers.email.get_email_backend"),
    ):
        instance = MagicMock()
        instance.send.side_effect = RuntimeError("ses throttled")
        svc_cls.return_value = instance
        from rentivo.jobs.handlers.email import handle_email_send

        with pytest.raises(RuntimeError, match="ses throttled"):
            handle_email_send(
                {
                    "event": "welcome",
                    "to_email": "alice@example.com",
                    "ctx": {},
                }
            )
