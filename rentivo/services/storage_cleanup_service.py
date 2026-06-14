from __future__ import annotations

import structlog

from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.billing_attachment import BillingAttachment
from rentivo.models.receipt import Receipt
from rentivo.observability import traced
from rentivo.repositories.base import BillingAttachmentRepository, BillRepository, ReceiptRepository
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

    Every method takes the acting principal first — a duck-typed object with
    ``.source`` / ``.user_id`` / ``.email`` (typically ``web.context.WebActor``,
    i.e. ``request.state.actor``) — mirroring ``JobService.enqueue_for``.
    """

    def __init__(
        self,
        job_service: JobService,
        bill_repo: BillRepository,
        receipt_repo: ReceiptRepository,
        attachment_repo: BillingAttachmentRepository | None = None,
    ) -> None:
        self.job_service = job_service
        self.bill_repo = bill_repo
        self.receipt_repo = receipt_repo
        self.attachment_repo = attachment_repo

    @traced("storage_cleanup.enqueue_key")
    def enqueue_key(self, actor, key: str | None) -> None:
        if not key:
            return
        self.job_service.enqueue_for(actor, "s3.delete", {"key": key})

    @traced("storage_cleanup.enqueue_receipt_delete")
    def enqueue_receipt_delete(self, actor, receipt: Receipt) -> None:
        self.enqueue_key(actor, receipt.storage_key)

    @traced("storage_cleanup.enqueue_bill_delete_cascade")
    def enqueue_bill_delete_cascade(self, actor, bill: Bill) -> None:
        if bill.id is not None:
            for receipt in self.receipt_repo.list_by_bill(bill.id):
                self.enqueue_key(actor, receipt.storage_key)
        self.enqueue_key(actor, bill.pdf_path or "")

    @traced("storage_cleanup.enqueue_attachment_delete")
    def enqueue_attachment_delete(self, actor, attachment: BillingAttachment) -> None:
        self.enqueue_key(actor, attachment.storage_key)

    @traced("storage_cleanup.enqueue_billing_delete_cascade")
    def enqueue_billing_delete_cascade(self, actor, billing: Billing) -> None:
        if billing.id is None:
            return
        for bill in self.bill_repo.list_by_billing(billing.id):
            self.enqueue_bill_delete_cascade(actor, bill)
        if self.attachment_repo is not None:
            for attachment in self.attachment_repo.list_by_billing(billing.id):
                self.enqueue_key(actor, attachment.storage_key)
