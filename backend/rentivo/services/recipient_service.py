from __future__ import annotations

import structlog

from rentivo.models.recipient import Recipient
from rentivo.observability import traced
from rentivo.repositories.base import RecipientRepository

logger = structlog.get_logger(__name__)


class RecipientService:
    def __init__(self, recipient_repo: RecipientRepository) -> None:
        self.recipient_repo = recipient_repo

    @traced("recipient.list_for_billing")
    def list_for_billing(self, billing_id: int) -> list[Recipient]:
        return self.recipient_repo.list_by_billing(billing_id)

    @traced("recipient.replace_for_billing")
    def replace_for_billing(self, billing_id: int, rows: list[dict[str, str]]) -> list[Recipient]:
        """Replace the billing's recipients from raw form rows.

        Rows are trimmed; any row missing a name OR an email is dropped — a
        recipient with no address cannot receive a communication.
        """
        recipients: list[Recipient] = []
        for row in rows:
            name = (row.get("name") or "").strip()
            email = (row.get("email") or "").strip()
            if not name or not email:
                continue
            recipients.append(Recipient(billing_id=billing_id, name=name, email=email))
        self.recipient_repo.replace_for_billing(billing_id, recipients)
        logger.info("recipients_replaced", billing_id=billing_id, count=len(recipients))
        return self.recipient_repo.list_by_billing(billing_id)
