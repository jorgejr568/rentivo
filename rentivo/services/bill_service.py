from __future__ import annotations

from datetime import datetime

import structlog

from rentivo.constants import SP_TZ
from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import Billing, ItemType
from rentivo.models.receipt import ALLOWED_RECEIPT_TYPES, MAX_RECEIPT_SIZE, Receipt
from rentivo.observability import traced
from rentivo.pdf.invoice import InvoicePDF
from rentivo.pdf.merger import merge_receipts
from rentivo.pix import generate_pix_payload, generate_pix_qrcode_png
from rentivo.repositories.base import BillRepository, ReceiptRepository
from rentivo.services.job_service import JobService
from rentivo.services.pix_service import PixConfig, PixService
from rentivo.settings import settings
from rentivo.storage.base import FileRef, StorageBackend

PIX_NOT_CONFIGURED_MESSAGE = "Configure a chave PIX, o nome e a cidade do recebedor antes de gerar faturas."

logger = structlog.get_logger(__name__)


CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


def _prefixed(path: str) -> str:
    """Prepend the configured storage prefix to a relative key, if any."""
    prefix = settings.storage_prefix
    return f"{prefix}/{path}" if prefix else path


def _storage_key(billing_uuid: str, bill_uuid: str) -> str:
    return _prefixed(f"{billing_uuid}/{bill_uuid}.pdf")


def _receipt_storage_key(billing_uuid: str, bill_uuid: str, receipt_uuid: str, content_type: str) -> str:
    ext = CONTENT_TYPE_EXTENSIONS.get(content_type, "")
    return _prefixed(f"{billing_uuid}/{bill_uuid}/receipts/{receipt_uuid}{ext}")


class BillService:
    def __init__(
        self,
        bill_repo: BillRepository,
        storage: StorageBackend,
        receipt_repo: ReceiptRepository | None = None,
        theme_service: object | None = None,
        pix_service: PixService | None = None,
        job_service: JobService | None = None,
    ) -> None:
        self.bill_repo = bill_repo
        self.storage = storage
        self.receipt_repo = receipt_repo
        self.theme_service = theme_service
        self.pix_service = pix_service
        self.job_service = job_service
        self.pdf_generator = InvoicePDF()

    def _resolve_pix(self, billing: Billing) -> PixConfig:
        if self.pix_service is None:
            raise ValueError(PIX_NOT_CONFIGURED_MESSAGE)
        config = self.pix_service.resolve_for_billing(billing)
        if config is None:
            raise ValueError(PIX_NOT_CONFIGURED_MESSAGE)
        return config

    def _get_pix_data(self, billing: Billing, total_centavos: int) -> tuple[bytes, str, str]:
        """Resolve PIX config and return (qrcode_png, pix_key, pix_payload).

        Raises ValueError when PIX is not configured — invoice generation must
        not proceed without a valid PIX configuration.
        """
        config = self._resolve_pix(billing)

        payload = generate_pix_payload(
            pix_key=config.pix_key,
            merchant_name=config.merchant_name,
            merchant_city=config.merchant_city,
            amount_centavos=total_centavos,
        )
        png = generate_pix_qrcode_png(
            pix_key=config.pix_key,
            merchant_name=config.merchant_name,
            merchant_city=config.merchant_city,
            amount_centavos=total_centavos,
            payload=payload,
        )
        return png, config.pix_key, payload

    def _fetch_receipt_data(self, bill: Bill) -> tuple[list[tuple[bytes, str]], list[Receipt]]:
        """Fetch receipt file data for a bill, for merging into the PDF.

        Returns (data, ordered_receipts) where ordered_receipts[i] corresponds
        to data[i]. Receipts whose file fetch fails are excluded from both lists
        but recorded in the log.
        """
        if self.receipt_repo is None or bill.id is None:
            return [], []
        receipts = self.receipt_repo.list_by_bill(bill.id)
        data: list[tuple[bytes, str]] = []
        ordered: list[Receipt] = []
        for receipt in receipts:
            try:
                blob = self.storage.get(receipt.storage_key)
                data.append((blob, receipt.content_type))
                ordered.append(receipt)
            except Exception:
                logger.exception(
                    "receipt_fetch_failed",
                    receipt_uuid=receipt.uuid,
                    storage_key=receipt.storage_key,
                )
        return data, ordered

    @traced("bill.render_pdf_sync")
    def _render_pdf_sync(self, bill: Bill, billing: Billing) -> tuple[str, list[str]]:
        """Generate PDF, save to storage, and update bill's pdf_path.

        Sets pdf_render_status='succeeded' on success. Used by the
        first-render path (generate_bill), the CLI (no JobService),
        and the pdf.render handler.

        Returns (storage_path, failed_receipt_uuids).
        """
        theme = None
        if self.theme_service is not None:
            theme = self.theme_service.resolve_theme_for_billing(billing)

        pix_png, pix_key, pix_payload = self._get_pix_data(billing, bill.total_amount)
        pdf_bytes = self.pdf_generator.generate(
            bill,
            billing.name,
            pix_qrcode_png=pix_png,
            pix_key=pix_key,
            pix_payload=pix_payload,
            theme=theme,
        )

        receipt_data, ordered_receipts = self._fetch_receipt_data(bill)
        failed_uuids: list[str] = []
        if receipt_data:
            pdf_bytes, failed_idxs = merge_receipts(pdf_bytes, receipt_data)
            if failed_idxs:
                failed_uuids = [ordered_receipts[i].uuid for i in failed_idxs if 0 <= i < len(ordered_receipts)]
                logger.warning(
                    "receipts_merge_failed",
                    bill_uuid=bill.uuid,
                    failed_receipt_uuids=failed_uuids,
                )

        key = _storage_key(billing.uuid, bill.uuid)
        path = self.storage.save(key, pdf_bytes)
        logger.info("bill_pdf_stored", bill_uuid=bill.uuid, storage_key=key)

        if bill.id is None:
            raise ValueError("Cannot update pdf_path for bill without an id")
        self.bill_repo.update_pdf_path(bill.id, path)
        self.bill_repo.update_pdf_render_status(bill.id, "succeeded")
        bill.pdf_path = path
        bill.pdf_render_status = "succeeded"
        return path, failed_uuids

    def _render_or_enqueue(self, bill: Bill, billing: Billing, actor=None) -> tuple[str | None, list[str]]:
        """Render synchronously when no JobService is configured (CLI),
        or enqueue a pdf.render job when one is (web).

        When ``actor`` is provided (typically ``request.state.actor`` on
        the web), the job is tagged with that actor via
        ``JobService.enqueue_for`` for audit purposes. When ``None`` —
        the CLI default — the job (if any) is tagged with empty
        source/id/username, matching the pre-refactor CLI behaviour.

        Returns (path, failed_uuids). In the enqueue branch path is None
        and failed_uuids is empty (the worker reports merge failures
        through the audit log).
        """
        if bill.id is None:
            raise ValueError("Cannot render or enqueue for bill without an id")
        if self.job_service is None:
            return self._render_pdf_sync(bill, billing)
        self.bill_repo.update_pdf_render_status(bill.id, "pending")
        bill.pdf_render_status = "pending"
        if actor is not None:
            self.job_service.enqueue_for(
                actor,
                "pdf.render",
                {"bill_id": bill.id},
                max_attempts=3,
            )
        else:
            self.job_service.enqueue(
                "pdf.render",
                {"bill_id": bill.id},
                source="",
                actor_id=None,
                actor_username="",
                max_attempts=3,
            )
        return None, []

    @traced("bill.generate")
    def generate_bill(
        self,
        billing: Billing,
        reference_month: str,
        variable_amounts: dict[int, int],
        extras: list[tuple[str, int]],
        notes: str = "",
        due_date: str = "",
        actor=None,
    ) -> Bill:
        line_items: list[BillLineItem] = []
        sort = 0

        for item in billing.items:
            if item.item_type == ItemType.FIXED:
                amount = item.amount
            else:
                if item.id is None:
                    raise ValueError("Variable billing item must have an id")
                amount = variable_amounts.get(item.id, 0)
            line_items.append(
                BillLineItem(
                    description=item.description,
                    amount=amount,
                    item_type=item.item_type,
                    sort_order=sort,
                )
            )
            sort += 1

        for desc, amt in extras:
            line_items.append(
                BillLineItem(
                    description=desc,
                    amount=amt,
                    item_type=ItemType.EXTRA,
                    sort_order=sort,
                )
            )
            sort += 1

        total = sum(li.amount for li in line_items)

        if billing.id is None:
            raise ValueError("Cannot generate bill for billing without an id")
        bill = Bill(
            billing_id=billing.id,
            reference_month=reference_month,
            total_amount=total,
            line_items=line_items,
            notes=notes,
            due_date=due_date or None,
        )
        bill = self.bill_repo.create(bill)
        logger.info(
            "bill_created",
            bill_id=bill.id,
            billing_id=billing.id,
            billing_name=billing.name,
            reference_month=reference_month,
            total_centavos=total,
        )

        self._render_or_enqueue(bill, billing, actor=actor)

        return bill

    def update_bill(
        self,
        bill: Bill,
        billing: Billing,
        line_items: list[BillLineItem],
        notes: str,
        due_date: str = "",
        actor=None,
    ) -> Bill:
        bill.line_items = line_items
        bill.total_amount = sum(li.amount for li in line_items)
        bill.notes = notes
        bill.due_date = due_date or None

        bill = self.bill_repo.update(bill)
        logger.info("bill_updated", bill_id=bill.id, total_centavos=bill.total_amount)

        self._render_or_enqueue(bill, billing, actor=actor)

        return bill

    def regenerate_pdf(self, bill: Bill, billing: Billing, actor=None) -> Bill:
        """Regenerate the PDF using current billing info (PIX key, etc.).

        With a JobService configured (web), enqueues a pdf.render job
        and returns immediately; bill.pdf_render_status is set to
        'pending'. Without one (CLI), renders synchronously.
        """
        logger.info("bill_pdf_regenerate", bill_uuid=bill.uuid)
        self._render_or_enqueue(bill, billing, actor=actor)
        return bill

    def get_invoice_url(self, pdf_path: str | None) -> str:
        if not pdf_path:
            return ""
        logger.debug("invoice_url_resolve", storage_key=pdf_path)
        return self.storage.get_url(pdf_path)

    def get_invoice_ref(self, bill: Bill) -> FileRef:
        """Resolve the bill's stored PDF to a FileRef (local path or URL).

        Callers must ensure ``bill.pdf_path`` is non-empty first.
        """
        logger.debug("invoice_ref_resolve", storage_key=bill.pdf_path)
        return self.storage.get_ref(bill.pdf_path or "")

    def get_receipt_ref(self, receipt: Receipt) -> FileRef:
        """Resolve a receipt's stored file to a FileRef (local path or URL).

        Callers must ensure ``receipt.storage_key`` is non-empty first.
        """
        logger.debug("receipt_ref_resolve", storage_key=receipt.storage_key)
        return self.storage.get_ref(receipt.storage_key)

    def list_bills(self, billing_id: int) -> list[Bill]:
        result = self.bill_repo.list_by_billing(billing_id)
        logger.debug("bills_listed", billing_id=billing_id, count=len(result))
        return result

    def change_status(self, bill: Bill, new_status: str) -> Bill:
        from rentivo.models.bill import BillStatus

        BillStatus(new_status)  # raises ValueError if invalid
        if bill.id is None:
            raise ValueError("Cannot change status for bill without an id")
        now = datetime.now(SP_TZ)
        self.bill_repo.update_status(bill.id, new_status, now)
        bill.status = new_status
        bill.status_updated_at = now
        logger.info("bill_status_changed", bill_id=bill.id, new_status=new_status)
        return bill

    def get_bill(self, bill_id: int) -> Bill | None:
        result = self.bill_repo.get_by_id(bill_id)
        logger.debug("bill_get", bill_id=bill_id, found=result is not None)
        return result

    def get_bill_by_uuid(self, uuid: str) -> Bill | None:
        result = self.bill_repo.get_by_uuid(uuid)
        logger.debug("bill_get_by_uuid", bill_uuid=uuid, found=result is not None)
        return result

    def delete_bill(self, bill_id: int) -> None:
        self.bill_repo.delete(bill_id)
        logger.info("bill_deleted", bill_id=bill_id)

    # ---- Receipt methods ----

    def add_receipt(
        self,
        bill: Bill,
        billing: Billing,
        filename: str,
        file_bytes: bytes,
        content_type: str,
        actor=None,
    ) -> tuple[Receipt, list[str]]:
        """Upload a receipt file and attach it to a bill, then regenerate the PDF.

        Returns (receipt, failed_receipt_uuids) — failed_receipt_uuids lists any
        existing receipts that could not be merged into the regenerated PDF.
        """
        if self.receipt_repo is None:
            raise RuntimeError("Receipt repository not configured")
        if bill.id is None:
            raise ValueError("Cannot add receipt to bill without an id")

        if content_type not in ALLOWED_RECEIPT_TYPES:
            raise ValueError(f"Unsupported file type: {content_type}")
        if len(file_bytes) > MAX_RECEIPT_SIZE:
            raise ValueError("File too large")
        if not file_bytes:
            raise ValueError("Empty file")

        from ulid import ULID

        receipt_uuid = str(ULID())
        storage_key = _receipt_storage_key(billing.uuid, bill.uuid, receipt_uuid, content_type)

        # Determine sort_order
        existing = self.receipt_repo.list_by_bill(bill.id)
        sort_order = max((r.sort_order for r in existing), default=-1) + 1

        # Store file
        self.storage.save(storage_key, file_bytes, content_type=content_type)

        try:
            receipt = Receipt(
                bill_id=bill.id,
                filename=filename,
                storage_key=storage_key,
                content_type=content_type,
                file_size=len(file_bytes),
                sort_order=sort_order,
            )
            receipt = self.receipt_repo.create(receipt)
        except Exception:
            logger.exception(
                "receipt_create_failed_cleanup",
                storage_key=storage_key,
            )
            self.storage.delete(storage_key)
            raise
        logger.info(
            "receipt_added",
            receipt_uuid=receipt.uuid,
            bill_uuid=bill.uuid,
            filename=filename,
        )

        _, failed_uuids = self._render_or_enqueue(bill, billing, actor=actor)
        return receipt, failed_uuids

    def delete_receipt(self, receipt: Receipt, bill: Bill, billing: Billing, actor=None) -> None:
        """Delete a receipt and regenerate the bill PDF."""
        if self.receipt_repo is None:
            raise RuntimeError("Receipt repository not configured")
        if receipt.id is None:
            raise ValueError("Cannot delete receipt without an id")

        self.receipt_repo.delete(receipt.id)
        logger.info("receipt_deleted", receipt_uuid=receipt.uuid, bill_uuid=bill.uuid)

        # Regenerate PDF without this receipt
        self._render_or_enqueue(bill, billing, actor=actor)

    def list_receipts(self, bill_id: int) -> list[Receipt]:
        """List receipts for a bill."""
        if self.receipt_repo is None:
            return []
        return self.receipt_repo.list_by_bill(bill_id)

    def get_receipt_by_uuid(self, uuid: str) -> Receipt | None:
        """Get a receipt by UUID."""
        if self.receipt_repo is None:
            return None
        return self.receipt_repo.get_by_uuid(uuid)

    def reorder_receipts(self, bill: Bill, billing: Billing, receipt_uuids: list[str], actor=None) -> None:
        """Reorder receipts by the given UUID list and regenerate the PDF."""
        if self.receipt_repo is None:
            raise RuntimeError("Receipt repository not configured")
        if bill.id is None:
            raise ValueError("Cannot reorder receipts for bill without an id")

        existing = self.receipt_repo.list_by_bill(bill.id)
        by_uuid = {r.uuid: r for r in existing}

        for uuid in receipt_uuids:
            if uuid not in by_uuid:
                raise ValueError(f"Receipt {uuid} does not belong to this bill")
        if len(receipt_uuids) != len(existing):
            raise ValueError("Must include all receipts in the new order")

        updates = [(by_uuid[uuid].id, idx) for idx, uuid in enumerate(receipt_uuids)]
        self.receipt_repo.update_sort_orders(updates)
        logger.info("receipts_reordered", bill_uuid=bill.uuid, count=len(updates))

        self._render_or_enqueue(bill, billing, actor=actor)
