from __future__ import annotations

from rentivo.models.communication import Communication
from rentivo.services.audit_serializers import serialize_communication


def test_serialize_communication_masks_recipient_pii():
    comm = Communication(
        id=3,
        uuid="COMMUUID",
        bill_id=5,
        comm_type="bill_ready",
        recipient_name="Rodrigo Silva",
        recipient_email="rodrigo@example.com",
        subject="Cobrança Joy 105",
        body_markdown="Prezado Rodrigo",
        status="queued",
    )
    data = serialize_communication(comm)
    assert data["uuid"] == "COMMUUID"
    assert data["comm_type"] == "bill_ready"
    assert data["status"] == "queued"
    # Email is partial-masked; raw value never appears.
    assert data["recipient_email"] == "ro...@example.com"
    assert "rodrigo@example.com" not in str(data)
    # Body is never logged.
    assert "body_markdown" not in data
