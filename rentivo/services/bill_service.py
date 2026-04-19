from __future__ import annotations

import logging
from datetime import datetime

from rentivo.constants import SP_TZ
from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import Billing, ItemType
from rentivo.models.receipt import ALLOWED_RECEIPT_TYPES, MAX_RECEIPT_SIZE, Receipt
from rentivo.pdf.invoice import InvoicePDF
from rentivo.pdf.merger import merge_receipts
from rentivo.pix import generate_pix_payload, generate_pix_qrcode_png
from rentivo.repositories.base import BillRepository, ReceiptRepository
from rentivo.settings import settings
from rentivo.storage.base import StorageBackend

logger = logging.getLogger(__name__)


CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


def _storage_key(billing_uuid: str, bill_uuid: str) -> str:
    prefix = settings.storage_prefix
    if prefix:
        return f"{prefix}/{billing_uuid}/{bill_uuid}.pdf"
    return f"{billing_uuid}/{bill_uuid}.pdf"


def _receipt_storage_key(billing_uuid: str, bill_uuid: str, receipt_uuid: str, content_type: str) -> str:
    ext = CONTENT_TYPE_EXTENSIONS.get(content_type, "")
    prefix = settings.storage_prefix
    if prefix:
        return f"{prefix}/{billing_uuid}/{bill_uuid}/receipts/{receipt_uuid}{ext}"
    return f"{billing_uuid}/{bill_uuid}/receipts/{receipt_uuid}{ext}"


class BillService:
    def __init__(
        self,
        bill_repo: BillRepository,
        storage: StorageBackend,
        receipt_repo: ReceiptRepository | None = None,
        theme_service: object | None = None,
    ) -> None:
        self.bill_repo = bill_repo
        self.storage = storage
        self.receipt_repo = receipt_repo
        self.theme_service = theme_service
        self.pdf_generator = InvoicePDF()

    @staticmethod
    def _get_pix_data(billing: Billing, total_centavos: int) -> tuple[bytes | None, str, str]:
        """Resolve PIX config and return (qrcode_png, pix_key, pix_payload)."""
        pix_key = billing.pix_key or settings.pix_key
        if not pix_key:
            return None, "", ""

        merchant_name = settings.pix_merchant_name
        merchant_city = settings.pix_merchant_city
        if not merchant_name or not merchant_city:
            return None, "", ""

        payload = generate_pix_payload(
            pix_key=pix_key,
            merchant_name=merchant_name,
            merchant_city=merchant_city,
            amount_centavos=total_centavos,
        )
        png = generate_pix_qrcode_png(
            pix_key=pix_key,
            merchant_name=merchant_name,
            merchant_city=merchant_city,
            amount_centavos=total_centavos,
            payload=payload,
        )
        return png, pix_key, payload

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
                    "Failed to fetch receipt %s (key=%s), skipping",
                    receipt.uuid,
                    receipt.storage_key,
                )
        return data, ordered

    def _generate_and_store_pdf(self, bill: Bill, billing: Billing) -> tuple[str, list[str]]:
        """Generate PDF, save to storage, and update bill's pdf_path.

        Returns (storage_path, failed_receipt_uuids) where failed_receipt_uuids
        lists receipts that could not be merged into the PDF.
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
                    "Receipts failed to merge for bill %s: %s",
                    bill.uuid,
                    failed_uuids,
                )

        key = _storage_key(billing.uuid, bill.uuid)
        path = self.storage.save(key, pdf_bytes)
        logger.info("PDF stored at %s for bill %s", key, bill.uuid)

        if bill.id is None:
            raise ValueError("Cannot update pdf_path for bill without an id")
        self.bill_repo.update_pdf_path(bill.id, path)
        bill.pdf_path = path
        return path, failed_uuids

    def generate_bill(
        self,
        billing: Billing,
        reference_month: str,
        variable_amounts: dict[int, int],
        extras: list[tuple[str, int]],
        notes: str = "",
        due_date: str = "",
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
            "Bill created: id=%s, billing=%s, month=%s, total=%d",
            bill.id,
            billing.name,
            reference_month,
            total,
        )

        self._generate_and_store_pdf(bill, billing)

        return bill

    def update_bill(
        self,
        bill: Bill,
        billing: Billing,
        line_items: list[BillLineItem],
        notes: str,
        due_date: str = "",
    ) -> Bill:
        bill.line_items = line_items
        bill.total_amount = sum(li.amount for li in line_items)
        bill.notes = notes
        bill.due_date = due_date or None

        bill = self.bill_repo.update(bill)
        logger.info("Bill updated: id=%s, total=%d", bill.id, bill.total_amount)

        self._generate_and_store_pdf(bill, billing)

        return bill

    def regenerate_pdf(self, bill: Bill, billing: Billing) -> Bill:
        """Regenerate the PDF using current billing info (PIX key, etc.)."""
        logger.info("Regenerating PDF for bill uuid=%s", bill.uuid)
        self._generate_and_store_pdf(bill, billing)
        return bill

    def get_invoice_url(self, pdf_path: str | None) -> str:
        if not pdf_path:
            return ""
        logger.debug("get_invoice_url key=%s", pdf_path)
        return self.storage.get_url(pdf_path)

    def list_bills(self, billing_id: int) -> list[Bill]:
        result = self.bill_repo.list_by_billing(billing_id)
        logger.debug("Listed %d bills for billing=%s", len(result), billing_id)
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
        logger.info("Bill %s status changed to %s", bill.id, new_status)
        return bill

    def get_bill(self, bill_id: int) -> Bill | None:
        result = self.bill_repo.get_by_id(bill_id)
        logger.debug("get_bill id=%s found=%s", bill_id, result is not None)
        return result

    def get_bill_by_uuid(self, uuid: str) -> Bill | None:
        result = self.bill_repo.get_by_uuid(uuid)
        logger.debug("get_bill_by_uuid uuid=%s found=%s", uuid, result is not None)
        return result

    def delete_bill(self, bill_id: int) -> None:
        self.bill_repo.delete(bill_id)
        logger.info("Bill %s soft-deleted", bill_id)

    # ---- Receipt methods ----

    def add_receipt(
        self,
        bill: Bill,
        billing: Billing,
        filename: str,
        file_bytes: bytes,
        content_type: str,
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
                "Receipt repo create failed, cleaning up orphaned storage key=%s",
                storage_key,
            )
            self.storage.delete(storage_key)
            raise
        logger.info("Receipt added: uuid=%s bill=%s file=%s", receipt.uuid, bill.uuid, filename)

        _, failed_uuids = self._generate_and_store_pdf(bill, billing)
        return receipt, failed_uuids

    def delete_receipt(self, receipt: Receipt, bill: Bill, billing: Billing) -> None:
        """Delete a receipt and regenerate the bill PDF."""
        if self.receipt_repo is None:
            raise RuntimeError("Receipt repository not configured")
        if receipt.id is None:
            raise ValueError("Cannot delete receipt without an id")

        self.receipt_repo.delete(receipt.id)
        logger.info("Receipt deleted: uuid=%s bill=%s", receipt.uuid, bill.uuid)

        # Regenerate PDF without this receipt
        self._generate_and_store_pdf(bill, billing)

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

    def reorder_receipts(self, bill: Bill, billing: Billing, receipt_uuids: list[str]) -> None:
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
        logger.info("Receipts reordered: bill=%s", bill.uuid)

        self._generate_and_store_pdf(bill, billing)
