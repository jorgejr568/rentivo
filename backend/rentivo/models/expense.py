from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class ExpenseCategory(str, Enum):
    IPTU = "iptu"
    CONDOMINIO = "condominio"
    MANUTENCAO = "manutencao"
    SEGURO = "seguro"
    OUTROS = "outros"


class Expense(BaseModel):
    id: int | None = None
    uuid: str = ""
    billing_id: int
    description: str
    amount: int = 0  # centavos
    category: str = ExpenseCategory.OUTROS.value
    incurred_on: str = ""  # 'YYYY-MM-DD'
    created_at: datetime | None = None
    deleted_at: datetime | None = None
