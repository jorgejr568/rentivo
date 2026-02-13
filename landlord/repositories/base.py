from abc import ABC, abstractmethod
from datetime import datetime

from landlord.models.bill import Bill
from landlord.models.billing import Billing
from landlord.models.invite import Invite
from landlord.models.organization import Organization, OrganizationMember
from landlord.models.user import User


class BillingRepository(ABC):
    @abstractmethod
    def create(self, billing: Billing) -> Billing: ...

    @abstractmethod
    def get_by_id(self, billing_id: int) -> Billing | None: ...

    @abstractmethod
    def get_by_uuid(self, uuid: str) -> Billing | None: ...

    @abstractmethod
    def list_all(self) -> list[Billing]: ...

    @abstractmethod
    def list_for_user(self, user_id: int) -> list[Billing]: ...

    @abstractmethod
    def update(self, billing: Billing) -> Billing: ...

    @abstractmethod
    def delete(self, billing_id: int) -> None: ...

    @abstractmethod
    def transfer_owner(self, billing_id: int, owner_type: str, owner_id: int) -> None: ...


class BillRepository(ABC):
    @abstractmethod
    def create(self, bill: Bill) -> Bill: ...

    @abstractmethod
    def get_by_id(self, bill_id: int) -> Bill | None: ...

    @abstractmethod
    def get_by_uuid(self, uuid: str) -> Bill | None: ...

    @abstractmethod
    def list_by_billing(self, billing_id: int) -> list[Bill]: ...

    @abstractmethod
    def update(self, bill: Bill) -> Bill: ...

    @abstractmethod
    def update_pdf_path(self, bill_id: int, pdf_path: str) -> None: ...

    @abstractmethod
    def update_paid_at(self, bill_id: int, paid_at: datetime | None) -> None: ...

    @abstractmethod
    def delete(self, bill_id: int) -> None: ...


class UserRepository(ABC):
    @abstractmethod
    def create(self, user: User) -> User: ...

    @abstractmethod
    def get_by_id(self, user_id: int) -> User | None: ...

    @abstractmethod
    def get_by_username(self, username: str) -> User | None: ...

    @abstractmethod
    def list_all(self) -> list[User]: ...

    @abstractmethod
    def update_password_hash(self, username: str, password_hash: str) -> None: ...


class OrganizationRepository(ABC):
    @abstractmethod
    def create(self, org: Organization) -> Organization: ...

    @abstractmethod
    def get_by_id(self, org_id: int) -> Organization | None: ...

    @abstractmethod
    def get_by_uuid(self, uuid: str) -> Organization | None: ...

    @abstractmethod
    def list_by_user(self, user_id: int) -> list[Organization]: ...

    @abstractmethod
    def update(self, org: Organization) -> Organization: ...

    @abstractmethod
    def delete(self, org_id: int) -> None: ...

    @abstractmethod
    def add_member(self, org_id: int, user_id: int, role: str) -> OrganizationMember: ...

    @abstractmethod
    def remove_member(self, org_id: int, user_id: int) -> None: ...

    @abstractmethod
    def get_member(self, org_id: int, user_id: int) -> OrganizationMember | None: ...

    @abstractmethod
    def list_members(self, org_id: int) -> list[OrganizationMember]: ...

    @abstractmethod
    def update_member_role(self, org_id: int, user_id: int, role: str) -> None: ...


class InviteRepository(ABC):
    @abstractmethod
    def create(self, invite: Invite) -> Invite: ...

    @abstractmethod
    def get_by_uuid(self, uuid: str) -> Invite | None: ...

    @abstractmethod
    def list_pending_for_user(self, user_id: int) -> list[Invite]: ...

    @abstractmethod
    def list_by_organization(self, org_id: int) -> list[Invite]: ...

    @abstractmethod
    def update_status(self, invite_id: int, status: str) -> None: ...

    @abstractmethod
    def count_pending_for_user(self, user_id: int) -> int: ...

    @abstractmethod
    def has_pending_invite(self, org_id: int, user_id: int) -> bool: ...
