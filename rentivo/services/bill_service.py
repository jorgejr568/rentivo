from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection

from rentivo.constants import SP_TZ
from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import Billing, ItemType
from rentivo.models.receipt import ALLOWED_RECEIPT_TYPES, MAX_RECEIPT_SIZE, Receipt
from rentivo.pdf.invoice import InvoicePDF
from rentivo.pdf.merger import merge_receipts
from rentivo.pix import generate_pix_payload, generate_pix_qrcode_png
from rentivo.repositories.base import BillRepository, ReceiptRepository
from rentivo.services._transaction import validate_transaction_binding
from rentivo.settings import settings
from rentivo.storage.base import StorageBackend

logger = logging.getLogger(__name__)


CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


@dataclass
class PdfWriteState:
    previous_pdf_path: str | None
    previous_pdf_bytes: bytes | None
    new_pdf_path: str | None = None


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
        db_conn: Connection | None = None,
    ) -> None:
        self.bill_repo = bill_repo
        self.storage = storage
        self.receipt_repo = receipt_repo
        self.theme_service = theme_service
        self.db_conn = db_conn
        validate_transaction_binding(self.db_conn, self.bill_repo, self.receipt_repo)
        self.pdf_generator = InvoicePDF()

    @property
    def transactional(self) -> bool:
        return self.db_conn is not None

    def _commit_transaction(self) -> None:
        if self.db_conn is not None:
            self.db_conn.commit()

    def _rollback_transaction(self) -> None:
        if self.db_conn is not None:
            self.db_conn.rollback()

    def _delete_storage_path(
        self,
        key: str,
        *,
        description: str,
        suppress_errors: bool = False,
    ) -> None:
        try:
            self.storage.delete(key)
        except Exception:
            logger.exception("Failed to delete %s from storage: %s", description, key)
            if not suppress_errors:
                raise

    def _load_existing_pdf_bytes(self, pdf_path: str | None) -> bytes | None:
        if not pdf_path:
            return None
        try:
            return self.storage.get(pdf_path)
        except Exception:
            logger.exception("Failed to load existing PDF for rollback: %s", pdf_path)
            return None

    def _restore_overwritten_pdf(
        self,
        previous_pdf_path: str | None,
        previous_pdf_bytes: bytes | None,
        new_pdf_path: str,
    ) -> None:
        if previous_pdf_path and previous_pdf_path == new_pdf_path and previous_pdf_bytes is not None:
            try:
                self.storage.save(new_pdf_path, previous_pdf_bytes)
                logger.info("Restored previous PDF after failed update: %s", new_pdf_path)
            except Exception:
                logger.exception("Failed to restore previous PDF after rollback: %s", new_pdf_path)
            return

        if new_pdf_path != previous_pdf_path:
            self._delete_storage_path(
                new_pdf_path,
                description="generated PDF during rollback",
                suppress_errors=True,
            )

    def _restore_receipt(self, receipt: Receipt) -> Receipt:
        if self.receipt_repo is None:
            raise RuntimeError("Receipt repository not configured")
        restored = self.receipt_repo.create(receipt.model_copy(deep=True))
        logger.warning("Receipt restored after rollback: uuid=%s bill_id=%s", receipt.uuid, receipt.bill_id)
        return restored

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

        amount = total_centavos / 100
        payload = generate_pix_payload(
            pix_key=pix_key,
            merchant_name=merchant_name,
            merchant_city=merchant_city,
            amount=amount,
        )
        png = generate_pix_qrcode_png(
            pix_key=pix_key,
            merchant_name=merchant_name,
            merchant_city=merchant_city,
            amount=amount,
            payload=payload,
        )
        return png, pix_key, payload

    def _fetch_receipt_data(self, bill: Bill) -> list[tuple[bytes, str]]:
        """Fetch receipt file data for a bill, for merging into the PDF."""
        if self.receipt_repo is None or bill.id is None:
            return []
        receipts = self.receipt_repo.list_by_bill(bill.id)
        result: list[tuple[bytes, str]] = []
        for receipt in receipts:
            try:
                data = self.storage.get(receipt.storage_key)
                result.append((data, receipt.content_type))
            except Exception:
                logger.exception(
                    "Failed to fetch receipt %s (key=%s), skipping",
                    receipt.uuid,
                    receipt.storage_key,
                )
        return result

    def _capture_pdf_write_state(self, bill: Bill) -> PdfWriteState:
        return PdfWriteState(
            previous_pdf_path=bill.pdf_path,
            previous_pdf_bytes=self._load_existing_pdf_bytes(bill.pdf_path),
        )

    def _restore_pdf_write_state(self, bill: Bill, pdf_state: PdfWriteState) -> None:
        if pdf_state.new_pdf_path is not None:
            self._restore_overwritten_pdf(
                pdf_state.previous_pdf_path,
                pdf_state.previous_pdf_bytes,
                pdf_state.new_pdf_path,
            )
        bill.pdf_path = pdf_state.previous_pdf_path

    @staticmethod
    def _restore_bill_snapshot(target: Bill, snapshot: Bill) -> None:
        target.reference_month = snapshot.reference_month
        target.total_amount = snapshot.total_amount
        target.line_items = [item.model_copy(deep=True) for item in snapshot.line_items]
        target.pdf_path = snapshot.pdf_path
        target.notes = snapshot.notes
        target.due_date = snapshot.due_date
        target.status = snapshot.status
        target.status_updated_at = snapshot.status_updated_at

    def _load_receipt_bytes_for_rollback(self, receipt: Receipt) -> bytes | None:
        try:
            return self.storage.get(receipt.storage_key)
        except Exception:
            logger.exception(
                "Failed to load receipt %s for rollback: %s",
                receipt.uuid,
                receipt.storage_key,
            )
            return None

    def _restore_receipt_file(self, receipt: Receipt, receipt_bytes: bytes | None) -> None:
        if receipt_bytes is None:
            return
        try:
            self.storage.save(receipt.storage_key, receipt_bytes, content_type=receipt.content_type)
            logger.info("Restored receipt file after rollback: %s", receipt.storage_key)
        except Exception:
            logger.exception("Failed to restore receipt file after rollback: %s", receipt.storage_key)

    def _generate_and_store_pdf(
        self,
        bill: Bill,
        billing: Billing,
        pdf_state: PdfWriteState | None = None,
    ) -> str:
        """Generate PDF, save to storage, and update bill's pdf_path. Returns the storage path."""
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

        # Merge receipts if available
        receipt_data = self._fetch_receipt_data(bill)
        if receipt_data:
            pdf_bytes = merge_receipts(pdf_bytes, receipt_data)

        key = _storage_key(billing.uuid, bill.uuid)
        pdf_state = pdf_state or self._capture_pdf_write_state(bill)
        path: str | None = None

        try:
            path = self.storage.save(key, pdf_bytes)
            logger.info("PDF stored at %s for bill %s", key, bill.uuid)

            if bill.id is None:
                raise ValueError("Cannot update pdf_path for bill without an id")
            self.bill_repo.update_pdf_path(bill.id, path)
            pdf_state.new_pdf_path = path
        except Exception:
            if path is not None:
                self._restore_overwritten_pdf(
                    pdf_state.previous_pdf_path,
                    pdf_state.previous_pdf_bytes,
                    path,
                )
            raise

        bill.pdf_path = path
        return path

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

        if self.transactional:
            pdf_state = PdfWriteState(previous_pdf_path=None, previous_pdf_bytes=None)
            try:
                self._generate_and_store_pdf(bill, billing, pdf_state=pdf_state)
                self._commit_transaction()
            except Exception:
                self._rollback_transaction()
                self._restore_pdf_write_state(bill, pdf_state)
                raise
            return bill

        try:
            self._generate_and_store_pdf(bill, billing)
        except Exception:
            if bill.id is not None:
                try:
                    self.bill_repo.delete(bill.id)
                    logger.warning("Rolled back bill creation after PDF failure: id=%s", bill.id)
                except Exception:
                    logger.exception("Failed to roll back bill creation: id=%s", bill.id)
            raise

        return bill

    def update_bill(
        self,
        bill: Bill,
        billing: Billing,
        line_items: list[BillLineItem],
        notes: str,
        due_date: str = "",
    ) -> Bill:
        previous_bill = bill.model_copy(deep=True)
        bill.line_items = line_items
        bill.total_amount = sum(li.amount for li in line_items)
        bill.notes = notes
        bill.due_date = due_date or None

        pdf_state = self._capture_pdf_write_state(previous_bill)
        bill = self.bill_repo.update(bill)
        logger.info("Bill updated: id=%s, total=%d", bill.id, bill.total_amount)

        if self.transactional:
            try:
                self._generate_and_store_pdf(bill, billing, pdf_state=pdf_state)
                self._commit_transaction()
            except Exception:
                self._rollback_transaction()
                self._restore_pdf_write_state(bill, pdf_state)
                self._restore_bill_snapshot(bill, previous_bill)
                raise
            return bill

        try:
            self._generate_and_store_pdf(bill, billing)
        except Exception:
            try:
                self.bill_repo.update(previous_bill)
                logger.warning("Rolled back bill update after PDF failure: id=%s", previous_bill.id)
            except Exception:
                logger.exception("Failed to roll back bill update: id=%s", previous_bill.id)
            raise

        return bill

    def regenerate_pdf(self, bill: Bill, billing: Billing) -> Bill:
        """Regenerate the PDF using current billing info (PIX key, etc.)."""
        logger.info("Regenerating PDF for bill uuid=%s", bill.uuid)
        if self.transactional:
            pdf_state = self._capture_pdf_write_state(bill)
            try:
                self._generate_and_store_pdf(bill, billing, pdf_state=pdf_state)
                self._commit_transaction()
            except Exception:
                self._rollback_transaction()
                self._restore_pdf_write_state(bill, pdf_state)
                raise
            return bill

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
    ) -> Receipt:
        """Upload a receipt file and attach it to a bill, then regenerate the PDF."""
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

        receipt = Receipt(
            uuid=receipt_uuid,
            bill_id=bill.id,
            filename=filename,
            storage_key=storage_key,
            content_type=content_type,
            file_size=len(file_bytes),
            sort_order=sort_order,
        )
        if self.transactional:
            pdf_state = self._capture_pdf_write_state(bill)
            try:
                receipt = self.receipt_repo.create(receipt)
                logger.info("Receipt added: uuid=%s bill=%s file=%s", receipt.uuid, bill.uuid, filename)
                self._generate_and_store_pdf(bill, billing, pdf_state=pdf_state)
                self._commit_transaction()
            except Exception:
                self._rollback_transaction()
                self._delete_storage_path(
                    storage_key,
                    description="receipt upload during rollback",
                    suppress_errors=True,
                )
                self._restore_pdf_write_state(bill, pdf_state)
                raise
            return receipt

        try:
            receipt = self.receipt_repo.create(receipt)
            logger.info("Receipt added: uuid=%s bill=%s file=%s", receipt.uuid, bill.uuid, filename)
        except Exception:
            existing_receipt = self.receipt_repo.get_by_uuid(receipt_uuid)
            if existing_receipt is not None and existing_receipt.id is not None:
                try:
                    self.receipt_repo.delete(existing_receipt.id)
                except Exception:
                    logger.exception("Failed to remove partially-created receipt: uuid=%s", receipt_uuid)
            self._delete_storage_path(
                storage_key,
                description="receipt upload during rollback",
                suppress_errors=True,
            )
            raise

        try:
            self._generate_and_store_pdf(bill, billing)
        except Exception:
            if receipt.id is not None:
                try:
                    self.receipt_repo.delete(receipt.id)
                except Exception:
                    logger.exception("Failed to roll back receipt row: uuid=%s", receipt.uuid)
            self._delete_storage_path(
                storage_key,
                description="receipt upload during rollback",
                suppress_errors=True,
            )
            raise

        return receipt

    def delete_receipt(self, receipt: Receipt, bill: Bill, billing: Billing) -> None:
        """Delete a receipt and regenerate the bill PDF."""
        if self.receipt_repo is None:
            raise RuntimeError("Receipt repository not configured")
        if receipt.id is None:
            raise ValueError("Cannot delete receipt without an id")

        if self.transactional:
            receipt_bytes = self._load_receipt_bytes_for_rollback(receipt)
            pdf_state = self._capture_pdf_write_state(bill)
            try:
                self._delete_storage_path(receipt.storage_key, description="receipt file")
                self.receipt_repo.delete(receipt.id)
                logger.info("Receipt deleted: uuid=%s bill=%s", receipt.uuid, bill.uuid)
                self._generate_and_store_pdf(bill, billing, pdf_state=pdf_state)
                self._commit_transaction()
            except Exception:
                self._rollback_transaction()
                self._restore_receipt_file(receipt, receipt_bytes)
                self._restore_pdf_write_state(bill, pdf_state)
                raise
            return

        self.receipt_repo.delete(receipt.id)
        logger.info("Receipt deleted: uuid=%s bill=%s", receipt.uuid, bill.uuid)

        try:
            self._generate_and_store_pdf(bill, billing)
        except Exception:
            try:
                self._restore_receipt(receipt)
            except Exception:
                logger.exception("Failed to restore receipt after PDF rollback: uuid=%s", receipt.uuid)
            raise

        try:
            self._delete_storage_path(receipt.storage_key, description="receipt file")
        except Exception:
            try:
                self._restore_receipt(receipt)
                self._generate_and_store_pdf(bill, billing)
            except Exception:
                logger.exception("Failed to restore receipt after storage cleanup failure: uuid=%s", receipt.uuid)
            raise

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
        previous_updates = [(receipt.id, receipt.sort_order) for receipt in existing]
        pdf_state = self._capture_pdf_write_state(bill)
        self.receipt_repo.update_sort_orders(updates)
        logger.info("Receipts reordered: bill=%s", bill.uuid)

        if self.transactional:
            try:
                self._generate_and_store_pdf(bill, billing, pdf_state=pdf_state)
                self._commit_transaction()
            except Exception:
                self._rollback_transaction()
                self._restore_pdf_write_state(bill, pdf_state)
                raise
            return

        try:
            self._generate_and_store_pdf(bill, billing)
        except Exception:
            try:
                self.receipt_repo.update_sort_orders(previous_updates)
                logger.warning("Rolled back receipt reorder after PDF failure: bill=%s", bill.uuid)
            except Exception:
                logger.exception("Failed to roll back receipt order: bill=%s", bill.uuid)
            raise
