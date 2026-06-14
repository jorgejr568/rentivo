from rentivo.email.base import EmailMessage
from rentivo.email.ses import SESEmailBackend


class _FakeSES:
    def send_email(self, **kwargs):
        return {"MessageId": "abc"}

    def send_raw_email(self, **kwargs):
        return {"MessageId": "raw"}


def _backend():
    b = SESEmailBackend.__new__(SESEmailBackend)
    b.from_address = "from@example.com"
    b.configuration_set = ""
    b.client = _FakeSES()
    return b


def _message():
    return EmailMessage(
        to="to@example.com",
        subject="s",
        text_body="t",
        html_body="<p>h</p>",
        from_address="from@example.com",
    )


def test_ses_send_emits_span(span_exporter):
    _backend().send(_message())
    assert "ses.send" in [s.name for s in span_exporter.get_finished_spans()]
