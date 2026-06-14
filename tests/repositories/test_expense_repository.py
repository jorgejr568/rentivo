import inspect

from rentivo.repositories.base import ExpenseRepository


def test_expense_repository_is_abstract():
    assert inspect.isabstract(ExpenseRepository)
    methods = set(ExpenseRepository.__abstractmethods__)
    assert methods == {"create", "get_by_uuid", "list_by_billing", "delete", "total_for_billings"}
