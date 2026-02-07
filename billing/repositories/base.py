from abc import ABC, abstractmethod

from billing.models.billing import Billing
from billing.models.bill import Bill


class BillingRepository(ABC):
    @abstractmethod
    def create(self, billing: Billing) -> Billing: ...

    @abstractmethod
    def get_by_id(self, billing_id: int) -> Billing | None: ...

    @abstractmethod
    def list_all(self) -> list[Billing]: ...

    @abstractmethod
    def delete(self, billing_id: int) -> None: ...


class BillRepository(ABC):
    @abstractmethod
    def create(self, bill: Bill) -> Bill: ...

    @abstractmethod
    def get_by_id(self, bill_id: int) -> Bill | None: ...

    @abstractmethod
    def list_by_billing(self, billing_id: int) -> list[Bill]: ...

    @abstractmethod
    def update(self, bill: Bill) -> Bill: ...

    @abstractmethod
    def update_pdf_path(self, bill_id: int, pdf_path: str) -> None: ...
