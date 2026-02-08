from __future__ import annotations

from datetime import datetime

from landlord.models.bill import Bill, BillLineItem
from landlord.models.billing import Billing, ItemType
from landlord.pdf.invoice import InvoicePDF
from landlord.pix import generate_pix_payload, generate_pix_qrcode_png
from landlord.repositories.base import BillRepository
from landlord.settings import settings
from landlord.storage.base import StorageBackend


class BillService:
    def __init__(self, bill_repo: BillRepository, storage: StorageBackend) -> None:
        self.bill_repo = bill_repo
        self.storage = storage
        self.pdf_generator = InvoicePDF()

    def _get_pix_data(
        self, billing: Billing, total_centavos: int
    ) -> tuple[bytes | None, str, str]:
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
        )
        return png, pix_key, payload

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
                amount = variable_amounts.get(item.id, 0)  # type: ignore[arg-type]
            line_items.append(
                BillLineItem(
                    description=item.description,
                    amount=amount,
                    item_type=item.item_type.value,
                    sort_order=sort,
                )
            )
            sort += 1

        for desc, amt in extras:
            line_items.append(
                BillLineItem(
                    description=desc,
                    amount=amt,
                    item_type="extra",
                    sort_order=sort,
                )
            )
            sort += 1

        total = sum(li.amount for li in line_items)

        bill = Bill(
            billing_id=billing.id,  # type: ignore[arg-type]
            reference_month=reference_month,
            total_amount=total,
            line_items=line_items,
            notes=notes,
            due_date=due_date or None,
        )
        bill = self.bill_repo.create(bill)

        pix_png, pix_key, pix_payload = self._get_pix_data(billing, total)
        pdf_bytes = self.pdf_generator.generate(
            bill, billing.name,
            pix_qrcode_png=pix_png, pix_key=pix_key, pix_payload=pix_payload,
        )
        key = f"{billing.uuid}/{bill.uuid}.pdf"
        path = self.storage.save(key, pdf_bytes)

        self.bill_repo.update_pdf_path(bill.id, path)  # type: ignore[arg-type]
        bill.pdf_path = path

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

        pix_png, pix_key, pix_payload = self._get_pix_data(billing, bill.total_amount)
        pdf_bytes = self.pdf_generator.generate(
            bill, billing.name,
            pix_qrcode_png=pix_png, pix_key=pix_key, pix_payload=pix_payload,
        )
        key = f"{billing.uuid}/{bill.uuid}.pdf"
        path = self.storage.save(key, pdf_bytes)

        self.bill_repo.update_pdf_path(bill.id, path)  # type: ignore[arg-type]
        bill.pdf_path = path

        return bill

    def regenerate_pdf(self, bill: Bill, billing: Billing) -> Bill:
        """Regenerate the PDF using current billing info (PIX key, etc.)."""
        pix_png, pix_key, pix_payload = self._get_pix_data(billing, bill.total_amount)
        pdf_bytes = self.pdf_generator.generate(
            bill, billing.name,
            pix_qrcode_png=pix_png, pix_key=pix_key, pix_payload=pix_payload,
        )
        key = f"{billing.uuid}/{bill.uuid}.pdf"
        path = self.storage.save(key, pdf_bytes)

        self.bill_repo.update_pdf_path(bill.id, path)  # type: ignore[arg-type]
        bill.pdf_path = path
        return bill

    def get_invoice_url(self, pdf_path: str | None) -> str:
        if not pdf_path:
            return ""
        return self.storage.get_presigned_url(pdf_path)

    def list_bills(self, billing_id: int) -> list[Bill]:
        return self.bill_repo.list_by_billing(billing_id)

    def toggle_paid(self, bill: Bill) -> Bill:
        if bill.paid_at is None:
            paid_at = datetime.now()
        else:
            paid_at = None
        self.bill_repo.update_paid_at(bill.id, paid_at)  # type: ignore[arg-type]
        bill.paid_at = paid_at
        return bill

    def get_bill(self, bill_id: int) -> Bill | None:
        return self.bill_repo.get_by_id(bill_id)
