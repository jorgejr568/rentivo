from rentivo.models.expense import Expense, ExpenseCategory


def test_category_values():
    assert ExpenseCategory.IPTU.value == "iptu"
    assert ExpenseCategory.CONDOMINIO.value == "condominio"
    assert ExpenseCategory.MANUTENCAO.value == "manutencao"
    assert ExpenseCategory.SEGURO.value == "seguro"
    assert ExpenseCategory.OUTROS.value == "outros"


def test_expense_defaults():
    e = Expense(
        billing_id=1,
        description="IPTU 2026",
        amount=12000,
        category="iptu",
        incurred_on="2026-01-10",
    )
    assert e.id is None
    assert e.uuid == ""
    assert e.deleted_at is None
    assert e.created_at is None
    assert e.amount == 12000
