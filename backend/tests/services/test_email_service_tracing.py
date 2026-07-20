from rentivo.email.base import EmailMessage
from rentivo.services.email_service import EmailService


class _FakeBackend:
    def send(self, message: EmailMessage) -> str:
        return "id"


def test_send_communication_emits_span(span_exporter):
    svc = EmailService(_FakeBackend(), from_address="from@example.com")
    svc.send_communication("to@example.com", "subj", "<p>body</p>", "body")
    assert "email.send_communication" in [s.name for s in span_exporter.get_finished_spans()]
