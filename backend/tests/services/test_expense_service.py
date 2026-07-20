import pytest

from rentivo.models.audit_log import AuditEventType
from rentivo.models.expense import Expense
from rentivo.services.audit_serializers import serialize_expense
from rentivo.services.expense_service import ExpenseService


def test_audit_event_types():
    assert AuditEventType.EXPENSE_CREATE == "expense.create"
    assert AuditEventType.EXPENSE_DELETE == "expense.delete"


def test_serialize_expense_omits_plaintext_description():
    e = Expense(
        id=5,
        uuid="01ABC",
        billing_id=2,
        description="SECRET reform",
        amount=900,
        category="manutencao",
        incurred_on="2026-04-02",
    )
    data = serialize_expense(e)
    assert data == {
        "id": 5,
        "uuid": "01ABC",
        "billing_id": 2,
        "amount": 900,
        "category": "manutencao",
        "incurred_on": "2026-04-02",
    }
    assert "description" not in data


class FakeExpenseRepo:
    def __init__(self):
        self.items: list[Expense] = []
        self._next = 1

    def create(self, expense):
        expense.id = self._next
        expense.uuid = f"u{self._next}"
        self._next += 1
        self.items.append(expense)
        return expense

    def get_by_uuid(self, uuid):
        return next((e for e in self.items if e.uuid == uuid and e.deleted_at is None), None)

    def list_by_billing(self, billing_id):
        return [e for e in self.items if e.billing_id == billing_id and e.deleted_at is None]

    def delete(self, expense_id):
        for e in self.items:
            if e.id == expense_id:
                from datetime import datetime

                e.deleted_at = datetime(2026, 1, 1)

    def total_for_billings(self, billing_ids):
        return sum(e.amount for e in self.items if e.billing_id in billing_ids and e.deleted_at is None)


def test_create_expense():
    svc = ExpenseService(FakeExpenseRepo())
    e = svc.create_expense(billing_id=1, description="IPTU", amount=12000, category="iptu", incurred_on="2026-01-10")
    assert e.id == 1
    assert e.description == "IPTU"


def test_list_for_billing():
    repo = FakeExpenseRepo()
    svc = ExpenseService(repo)
    svc.create_expense(billing_id=1, description="A", amount=100, category="iptu", incurred_on="2026-01-01")
    svc.create_expense(billing_id=2, description="B", amount=200, category="outros", incurred_on="2026-01-01")
    assert [e.description for e in svc.list_for_billing(1)] == ["A"]


def test_get_by_uuid_and_delete():
    repo = FakeExpenseRepo()
    svc = ExpenseService(repo)
    e = svc.create_expense(billing_id=1, description="A", amount=100, category="iptu", incurred_on="2026-01-01")
    assert svc.get_by_uuid(e.uuid) is not None
    svc.delete_expense(e)
    assert svc.get_by_uuid(e.uuid) is None


def test_delete_expense_without_id_raises():
    svc = ExpenseService(FakeExpenseRepo())
    with pytest.raises(ValueError):
        svc.delete_expense(Expense(billing_id=1, description="x", amount=1, category="iptu", incurred_on="2026-01-01"))
