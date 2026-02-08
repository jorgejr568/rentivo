from __future__ import annotations

from datetime import datetime

from landlord.models.bill import SP_TZ, Bill, BillLineItem
from landlord.models.billing import Billing, ItemType
from landlord.pdf.invoice import InvoicePDF
from landlord.pix import generate_pix_payload, generate_pix_qrcode_png
from landlord.repositories.base import BillRepository
from landlord.settings import settings
from landlord.storage.base import StorageBackend


def _storage_key(billing_uuid: str, bill_uuid: str) -> str:
    prefix = settings.storage_prefix
    if prefix:
        return f"{prefix}/{billing_uuid}/{bill_uuid}.pdf"
    return f"{billing_uuid}/{bill_uuid}.pdf"


class BillService:
    def __init__(self, bill_repo: BillRepository, storage: StorageBackend) -> None:
        self.bill_repo = bill_repo
        self.storage = storage
        self.pdf_generator = InvoicePDF()

    @staticmethod
    def _get_pix_data(
        billing: Billing, total_centavos: int
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
                assert item.id is not None
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

        assert billing.id is not None
        bill = Bill(
            billing_id=billing.id,
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
        key = _storage_key(billing.uuid, bill.uuid)
        path = self.storage.save(key, pdf_bytes)

        assert bill.id is not None
        self.bill_repo.update_pdf_path(bill.id, path)
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
        key = _storage_key(billing.uuid, bill.uuid)
        path = self.storage.save(key, pdf_bytes)

        assert bill.id is not None
        self.bill_repo.update_pdf_path(bill.id, path)
        bill.pdf_path = path

        return bill

    def regenerate_pdf(self, bill: Bill, billing: Billing) -> Bill:
        """Regenerate the PDF using current billing info (PIX key, etc.)."""
        pix_png, pix_key, pix_payload = self._get_pix_data(billing, bill.total_amount)
        pdf_bytes = self.pdf_generator.generate(
            bill, billing.name,
            pix_qrcode_png=pix_png, pix_key=pix_key, pix_payload=pix_payload,
        )
        key = _storage_key(billing.uuid, bill.uuid)
        path = self.storage.save(key, pdf_bytes)

        assert bill.id is not None
        self.bill_repo.update_pdf_path(bill.id, path)
        bill.pdf_path = path
        return bill

    def get_invoice_url(self, pdf_path: str | None) -> str:
        if not pdf_path:
            return ""
        return self.storage.get_url(pdf_path)

    def list_bills(self, billing_id: int) -> list[Bill]:
        return self.bill_repo.list_by_billing(billing_id)

    def toggle_paid(self, bill: Bill) -> Bill:
        if bill.paid_at is None:
            paid_at = datetime.now(SP_TZ)
        else:
            paid_at = None
        assert bill.id is not None
        self.bill_repo.update_paid_at(bill.id, paid_at)
        bill.paid_at = paid_at
        return bill

    def get_bill(self, bill_id: int) -> Bill | None:
        return self.bill_repo.get_by_id(bill_id)

    def get_bill_by_uuid(self, uuid: str) -> Bill | None:
        return self.bill_repo.get_by_uuid(uuid)

    def delete_bill(self, bill_id: int) -> None:
        self.bill_repo.delete(bill_id)
