from __future__ import annotations

from datetime import datetime

import structlog

from rentivo.constants import SP_TZ
from rentivo.models.bill import Bill, BillLineItem, BillStatus, InvalidStatusTransition, is_transition_allowed
from rentivo.models.billing import Billing, ItemType
from rentivo.models.receipt import ALLOWED_RECEIPT_TYPES, MAX_RECEIPT_SIZE, Receipt
from rentivo.models.recipient import Recipient
from rentivo.observability import traced
from rentivo.pdf.invoice import InvoicePDF
from rentivo.pdf.merger import merge_receipts
from rentivo.pdf.recibo import ReciboPDF
from rentivo.pix import generate_pix_payload, generate_pix_qrcode_png
from rentivo.repositories.base import BillRepository, ReceiptRepository
from rentivo.services.job_service import JobService
from rentivo.services.pix_service import PixConfig, PixService
from rentivo.settings import settings
from rentivo.storage.base import FileRef, StorageBackend
from rentivo.whatsapp import build_invoice_message, build_whatsapp_link

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


def _recibo_storage_key(billing_uuid: str, bill_uuid: str) -> str:
    return _prefixed(f"{billing_uuid}/{bill_uuid}.recibo.pdf")


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
        self.recibo_generator = ReciboPDF()

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

    @traced("bill.whatsapp_link")
    def build_whatsapp_link(self, bill: Bill, billing: Billing, recipient: Recipient) -> str | None:
        """Build a ``wa.me`` deep link to send this bill to ``recipient`` over WhatsApp.

        The prefilled message carries the invoice essentials (unit, month,
        amount, due date) plus the PIX copia-e-cola string so the tenant can pay
        from the chat. Returns ``None`` when the recipient has no usable phone
        number. Raises ``ValueError`` (via ``_get_pix_data``) when PIX is not
        configured, since the message is worthless without the copia-e-cola.
        """
        _, _, payload = self._get_pix_data(billing, bill.total_amount)
        message = build_invoice_message(
            billing_name=billing.name,
            reference_month=bill.reference_month,
            amount_centavos=bill.total_amount,
            due_date=bill.due_date,
            pix_payload=payload,
        )
        return build_whatsapp_link(recipient.phone, message)

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
        render: bool = True,
    ) -> Bill:
        """Create a bill and render/enqueue its PDF.

        ``render=False`` skips the PDF step so a caller that will attach
        receipts first can render exactly once afterwards (see the web
        ``bill_generate`` flow). Defaults to ``True`` — the CLI and any caller
        without follow-up work get the first-render behaviour unchanged.
        """
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

        if render:
            self._render_or_enqueue(bill, billing, actor=actor)

        return bill

    @traced("bill.update_bill")
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

    @traced("bill.regenerate_pdf")
    def regenerate_pdf(self, bill: Bill, billing: Billing, actor=None) -> Bill:
        """Regenerate the PDF using current billing info (PIX key, etc.).

        With a JobService configured (web), enqueues a pdf.render job
        and returns immediately; bill.pdf_render_status is set to
        'pending'. Without one (CLI), renders synchronously.

        When the bill is already PAID, the payment receipt (recibo) is
        regenerated alongside the invoice — the recibo embeds the same billing
        info (issuer, PIX), so re-rendering only the invoice would leave a stale
        quittance behind. The recibo render goes through the same enqueue/sync
        path and the ``recibo.render`` handler re-checks PAID, so a status that
        reverts before the job runs produces no orphan recibo.
        """
        logger.info("bill_pdf_regenerate", bill_uuid=bill.uuid)
        self._render_or_enqueue(bill, billing, actor=actor)
        if bill.status == BillStatus.PAID.value:
            self._enqueue_or_render_recibo(bill, billing, actor=actor)
        return bill

    def _resolve_recibo_issuer(self, billing: Billing) -> str:
        """Issuer ("EMITENTE") shown on the recibo: the organization name for
        org-owned billings, the account email for user-owned billings. Falls
        back to the billing name when the owner can't be resolved (no
        pix_service, missing owner row, or empty name)."""
        if self.pix_service is not None and billing.owner_id is not None:
            if billing.owner_type == "organization":
                org = self.pix_service.org_repo.get_by_id(billing.owner_id)
                if org is not None and org.name:
                    return org.name
            else:
                user = self.pix_service.user_repo.get_by_id(billing.owner_id)
                if user is not None and user.email:
                    return user.email
        return billing.name

    @traced("bill.render_recibo")
    def render_recibo(self, bill: Bill, billing: Billing) -> bytes:
        """Render a payment-receipt ("Recibo de Pagamento") PDF on the fly.

        Unlike the invoice, the recibo is NOT persisted to storage — the bytes
        are returned for the caller to stream. The payer is the billing name;
        the issuer is the billing owner (organization name or account email,
        falling back to the billing name). The payment date is the bill's
        status-change timestamp (when the bill moved to PAID), DD/MM/YYYY.
        """
        theme = None
        if self.theme_service is not None:
            theme = self.theme_service.resolve_theme_for_billing(billing)

        issuer_name = self._resolve_recibo_issuer(billing)
        payment_date = ""
        if bill.status_updated_at is not None:
            payment_date = bill.status_updated_at.strftime("%d/%m/%Y")

        pdf_bytes = self.recibo_generator.generate(
            bill,
            billing_name=billing.name,
            issuer_name=issuer_name,
            payment_date=payment_date,
            theme=theme,
        )
        logger.info("recibo_rendered", bill_uuid=bill.uuid, bytes=len(pdf_bytes))
        return pdf_bytes

    @traced("bill.store_recibo")
    def store_recibo(self, bill: Bill, billing: Billing) -> str:
        """Render the recibo and persist it to storage, recording its key.

        Used by the ``recibo.render`` background job (web) and the synchronous
        fallback when no JobService is configured (CLI). Returns the storage key
        and stamps it onto ``bill.recibo_pdf_path``.
        """
        if bill.id is None:
            raise ValueError("Cannot store recibo for bill without an id")
        pdf_bytes = self.render_recibo(bill, billing)
        key = _recibo_storage_key(billing.uuid, bill.uuid)
        path = self.storage.save(key, bytes(pdf_bytes), content_type="application/pdf")
        self.bill_repo.update_recibo_pdf_path(bill.id, path)
        bill.recibo_pdf_path = path
        logger.info("recibo_stored", bill_uuid=bill.uuid, storage_key=key)
        return path

    def _enqueue_or_render_recibo(self, bill: Bill, billing: Billing | None, actor=None) -> None:
        """Render the recibo synchronously (CLI) or enqueue a ``recibo.render``
        job (web). Called from ``change_status``, which has already validated
        ``bill.id`` is set."""
        if self.job_service is None:
            if billing is not None:
                self.store_recibo(bill, billing)
            return
        if actor is not None:
            self.job_service.enqueue_for(actor, "recibo.render", {"bill_id": bill.id}, max_attempts=3)
        else:
            self.job_service.enqueue(
                "recibo.render",
                {"bill_id": bill.id},
                source="",
                actor_id=None,
                actor_username="",
                max_attempts=3,
            )

    def _remove_recibo(self, bill: Bill, actor=None) -> None:
        """Delete a stored recibo and clear its key. Called when a bill leaves
        the PAID status (the quittance no longer reflects reality). Called from
        ``change_status``, which has already validated ``bill.id`` is set."""
        key = bill.recibo_pdf_path
        if not key:
            return
        if self.job_service is None:
            try:
                self.storage.delete(key)
            except Exception:
                logger.exception("recibo_delete_failed", bill_uuid=bill.uuid, storage_key=key)
        elif actor is not None:
            self.job_service.enqueue_for(actor, "s3.delete", {"key": key})
        else:
            self.job_service.enqueue("s3.delete", {"key": key}, source="", actor_id=None, actor_username="")
        self.bill_repo.update_recibo_pdf_path(bill.id, None)
        bill.recibo_pdf_path = None
        logger.info("recibo_removed", bill_uuid=bill.uuid, storage_key=key)

    @traced("bill.get_recibo_ref")
    def get_recibo_ref(self, bill: Bill) -> FileRef:
        """Resolve the bill's stored recibo to a FileRef (local path or URL).

        Callers must ensure ``bill.recibo_pdf_path`` is non-empty first.
        """
        logger.debug("recibo_ref_resolve", storage_key=bill.recibo_pdf_path)
        return self.storage.get_ref(bill.recibo_pdf_path or "")

    @traced("bill.get_invoice_url")
    def get_invoice_url(self, pdf_path: str | None) -> str:
        if not pdf_path:
            return ""
        logger.debug("invoice_url_resolve", storage_key=pdf_path)
        return self.storage.get_url(pdf_path)

    @traced("bill.get_invoice_ref")
    def get_invoice_ref(self, bill: Bill) -> FileRef:
        """Resolve the bill's stored PDF to a FileRef (local path or URL).

        Callers must ensure ``bill.pdf_path`` is non-empty first.
        """
        logger.debug("invoice_ref_resolve", storage_key=bill.pdf_path)
        return self.storage.get_ref(bill.pdf_path or "")

    @traced("bill.get_receipt_ref")
    def get_receipt_ref(self, receipt: Receipt) -> FileRef:
        """Resolve a receipt's stored file to a FileRef (local path or URL).

        Callers must ensure ``receipt.storage_key`` is non-empty first.
        """
        logger.debug("receipt_ref_resolve", storage_key=receipt.storage_key)
        return self.storage.get_ref(receipt.storage_key)

    @traced("bill.list_bills")
    def list_bills(self, billing_id: int) -> list[Bill]:
        result = self.bill_repo.list_by_billing(billing_id)
        logger.debug("bills_listed", billing_id=billing_id, count=len(result))
        return result

    @traced("bill.change_status")
    def change_status(self, bill: Bill, new_status: str, billing: Billing | None = None, actor=None) -> Bill:
        BillStatus(new_status)  # raises ValueError if invalid
        if bill.id is None:
            raise ValueError("Cannot change status for bill without an id")
        # Defense-in-depth: enforce the lifecycle server-side so a crafted POST
        # cannot perform any-to-any transitions (e.g. paid → draft) that the UI
        # never offers. Source of truth is ALLOWED_STATUS_TRANSITIONS (REN-21).
        if not is_transition_allowed(bill.status, new_status):
            logger.warning(
                "bill_status_transition_rejected",
                bill_id=bill.id,
                current_status=bill.status,
                new_status=new_status,
            )
            raise InvalidStatusTransition(bill.status, new_status)
        previous_status = bill.status
        now = datetime.now(SP_TZ)
        self.bill_repo.update_status(bill.id, new_status, now)
        bill.status = new_status
        bill.status_updated_at = now
        logger.info("bill_status_changed", bill_id=bill.id, new_status=new_status)

        # Payment-receipt lifecycle: generate the recibo in the background when a
        # bill becomes PAID, and tear it down when it leaves PAID (the quittance
        # would otherwise outlive the payment it certifies). Transitions between
        # two non-PAID statuses — and re-saving PAID — touch nothing extra.
        paid = BillStatus.PAID.value
        if new_status == paid and previous_status != paid:
            self._enqueue_or_render_recibo(bill, billing, actor=actor)
        elif previous_status == paid and new_status != paid:
            self._remove_recibo(bill, actor=actor)
        return bill

    @traced("bill.get_bill")
    def get_bill(self, bill_id: int) -> Bill | None:
        result = self.bill_repo.get_by_id(bill_id)
        logger.debug("bill_get", bill_id=bill_id, found=result is not None)
        return result

    @traced("bill.get_bill_by_uuid")
    def get_bill_by_uuid(self, uuid: str) -> Bill | None:
        result = self.bill_repo.get_by_uuid(uuid)
        logger.debug("bill_get_by_uuid", bill_uuid=uuid, found=result is not None)
        return result

    @traced("bill.delete_bill")
    def delete_bill(self, bill_id: int) -> None:
        self.bill_repo.delete(bill_id)
        logger.info("bill_deleted", bill_id=bill_id)

    # ---- Receipt methods ----

    @traced("bill.add_receipt")
    def add_receipt(
        self,
        bill: Bill,
        billing: Billing,
        filename: str,
        file_bytes: bytes,
        content_type: str,
        actor=None,
        render: bool = True,
    ) -> tuple[Receipt, list[str]]:
        """Upload a receipt file and attach it to a bill, then regenerate the PDF.

        Returns (receipt, failed_receipt_uuids) — failed_receipt_uuids lists any
        existing receipts that could not be merged into the regenerated PDF.

        ``render=False`` attaches the receipt without rendering, so a caller
        adding several receipts (or creating a bill) can render exactly once at
        the end instead of once per receipt. Defaults to ``True`` so the
        standalone receipt-upload endpoint re-renders on every upload.
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

        if render:
            _, failed_uuids = self._render_or_enqueue(bill, billing, actor=actor)
        else:
            failed_uuids = []
        return receipt, failed_uuids

    @traced("bill.delete_receipt")
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

    @traced("bill.list_receipts")
    def list_receipts(self, bill_id: int) -> list[Receipt]:
        """List receipts for a bill."""
        if self.receipt_repo is None:
            return []
        return self.receipt_repo.list_by_bill(bill_id)

    @traced("bill.get_receipt_by_uuid")
    def get_receipt_by_uuid(self, uuid: str) -> Receipt | None:
        """Get a receipt by UUID."""
        if self.receipt_repo is None:
            return None
        return self.receipt_repo.get_by_uuid(uuid)

    @traced("bill.reorder_receipts")
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
