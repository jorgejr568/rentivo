from __future__ import annotations

from billing.models.billing import Billing, BillingItem
from billing.repositories.base import BillingRepository


class BillingService:
    def __init__(self, repo: BillingRepository) -> None:
        self.repo = repo

    def create_billing(
        self, name: str, description: str, items: list[BillingItem], pix_key: str = ""
    ) -> Billing:
        billing = Billing(name=name, description=description, items=items, pix_key=pix_key)
        return self.repo.create(billing)

    def list_billings(self) -> list[Billing]:
        return self.repo.list_all()

    def get_billing(self, billing_id: int) -> Billing | None:
        return self.repo.get_by_id(billing_id)

    def delete_billing(self, billing_id: int) -> None:
        self.repo.delete(billing_id)
