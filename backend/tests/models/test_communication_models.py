from __future__ import annotations

from rentivo.models.communication import Communication, CommunicationTemplate


def test_communication_template_defaults():
    t = CommunicationTemplate(
        owner_type="billing",
        owner_id=1,
        comm_type="bill_ready",
        subject="s",
        body_markdown="b",
    )
    assert t.id is None and t.uuid == "" and t.created_at is None and t.updated_at is None


def test_communication_defaults():
    c = Communication(
        bill_id=5,
        comm_type="bill_ready",
        recipient_name="R",
        recipient_email="r@x.com",
        subject="s",
        body_markdown="b",
    )
    assert c.status == "queued"
    assert c.error == "" and c.job_ulid == ""
    assert c.id is None and c.uuid == "" and c.sent_at is None
