from __future__ import annotations

from email import message_from_bytes

from rentivo.email.base import EmailBackend, EmailMessage
from rentivo.email.local import LocalEmailBackend
from rentivo.email.mime import build_mime
from rentivo.services.email_service import EmailService


def _msg(**over):
    base = dict(to="a@x.com", subject="s", text_body="t", html_body="<p>t</p>", from_address="n@x.com")
    base.update(over)
    return EmailMessage(**base)


def test_email_message_headers_default_empty():
    assert _msg().headers == ()


def test_build_mime_sets_unique_message_id():
    a = build_mime(_msg())
    b = build_mime(_msg())
    assert a["Message-ID"] and b["Message-ID"]
    assert a["Message-ID"] != b["Message-ID"]


def test_build_mime_applies_custom_headers():
    mime = build_mime(_msg(headers=(("X-Entity-Ref-ID", "01ABC"),)))
    assert mime["X-Entity-Ref-ID"] == "01ABC"


def test_local_eml_carries_entity_ref(tmp_path):
    path = LocalEmailBackend(str(tmp_path)).send(_msg(headers=(("X-Entity-Ref-ID", "01XYZ"),)))
    parsed = message_from_bytes(open(path, "rb").read())
    assert parsed["X-Entity-Ref-ID"] == "01XYZ"
    assert parsed["Message-ID"]


class _Capturing(EmailBackend):
    def __init__(self):
        self.sent = None

    def send(self, message):
        self.sent = message
        return "id"


def test_send_communication_threads_headers():
    backend = _Capturing()
    EmailService(backend, from_address="n@x.com").send_communication(
        "a@x.com", "s", "<p>b</p>", "b", headers=(("X-Entity-Ref-ID", "01COMM"),)
    )
    assert ("X-Entity-Ref-ID", "01COMM") in backend.sent.headers
