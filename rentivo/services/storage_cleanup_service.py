from __future__ import annotations

import structlog

from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.receipt import Receipt
from rentivo.repositories.base import BillRepository, ReceiptRepository
from rentivo.services.job_service import JobService

logger = structlog.get_logger(__name__)


class StorageCleanupService:
    """Enqueue ``s3.delete`` jobs for every key orphaned by a row deletion.

    The cascade rules are documented in
    docs/superpowers/specs/2026-05-02-s3-delete-job-design.md. In short:

    - delete_receipt -> 1 job (the receipt's storage_key)
    - delete_bill    -> N+1 jobs (each receipt + the bill PDF)
    - delete_billing -> walks bills then receipts under each bill

    Empty keys are silently skipped -- bills can have ``pdf_path=""`` if a
    PDF render previously failed.
    """

    def __init__(
        self,
        job_service: JobService,
        bill_repo: BillRepository,
        receipt_repo: ReceiptRepository,
    ) -> None:
        self.job_service = job_service
        self.bill_repo = bill_repo
        self.receipt_repo = receipt_repo

    def enqueue_key(
        self,
        key: str | None,
        *,
        source: str = "web",
        actor_id: int | None = None,
        actor_username: str = "",
    ) -> None:
        if not key:
            return
        self.job_service.enqueue(
            "s3.delete",
            {"key": key},
            source=source,
            actor_id=actor_id,
            actor_username=actor_username,
        )

    def enqueue_receipt_delete(
        self,
        receipt: Receipt,
        *,
        source: str = "web",
        actor_id: int | None = None,
        actor_username: str = "",
    ) -> None:
        self.enqueue_key(
            receipt.storage_key,
            source=source,
            actor_id=actor_id,
            actor_username=actor_username,
        )

    def enqueue_bill_delete_cascade(
        self,
        bill: Bill,
        *,
        source: str = "web",
        actor_id: int | None = None,
        actor_username: str = "",
    ) -> None:
        if bill.id is not None:
            for receipt in self.receipt_repo.list_by_bill(bill.id):
                self.enqueue_key(
                    receipt.storage_key,
                    source=source,
                    actor_id=actor_id,
                    actor_username=actor_username,
                )
        self.enqueue_key(
            bill.pdf_path or "",
            source=source,
            actor_id=actor_id,
            actor_username=actor_username,
        )

    def enqueue_billing_delete_cascade(
        self,
        billing: Billing,
        *,
        source: str = "web",
        actor_id: int | None = None,
        actor_username: str = "",
    ) -> None:
        if billing.id is None:
            return
        for bill in self.bill_repo.list_by_billing(billing.id):
            self.enqueue_bill_delete_cascade(
                bill,
                source=source,
                actor_id=actor_id,
                actor_username=actor_username,
            )
