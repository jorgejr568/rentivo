from __future__ import annotations

import structlog

from rentivo.models.expense import Expense
from rentivo.observability import traced
from rentivo.repositories.base import ExpenseRepository

logger = structlog.get_logger(__name__)


class ExpenseService:
    def __init__(self, expense_repo: ExpenseRepository) -> None:
        self.expense_repo = expense_repo

    @traced("expense.create_expense")
    def create_expense(
        self, *, billing_id: int, description: str, amount: int, category: str, incurred_on: str
    ) -> Expense:
        expense = Expense(
            billing_id=billing_id,
            description=description,
            amount=amount,
            category=category,
            incurred_on=incurred_on,
        )
        created = self.expense_repo.create(expense)
        logger.info(
            "expense_created",
            expense_uuid=created.uuid,
            billing_id=billing_id,
            amount=amount,
            category=category,
        )
        return created

    @traced("expense.list_for_billing")
    def list_for_billing(self, billing_id: int) -> list[Expense]:
        return self.expense_repo.list_by_billing(billing_id)

    @traced("expense.get_by_uuid")
    def get_by_uuid(self, uuid: str) -> Expense | None:
        return self.expense_repo.get_by_uuid(uuid)

    @traced("expense.delete_expense")
    def delete_expense(self, expense: Expense) -> None:
        if expense.id is None:
            raise ValueError("Cannot delete expense without an id")
        self.expense_repo.delete(expense.id)
        logger.info("expense_deleted", expense_uuid=expense.uuid)
