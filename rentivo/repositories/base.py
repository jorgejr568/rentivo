from abc import ABC, abstractmethod
from datetime import datetime

from rentivo.models.audit_log import AuditLog
from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.invite import Invite
from rentivo.models.mfa import RecoveryCode, UserPasskey, UserTOTP
from rentivo.models.organization import Organization, OrganizationMember
from rentivo.models.receipt import Receipt
from rentivo.models.user import User


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

    @abstractmethod
    def user_has_enforcing_org(self, user_id: int) -> bool: ...


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


class AuditLogRepository(ABC):
    @abstractmethod
    def create(self, audit_log: AuditLog) -> AuditLog: ...

    @abstractmethod
    def list_by_entity(self, entity_type: str, entity_id: int) -> list[AuditLog]: ...

    @abstractmethod
    def list_by_actor(self, actor_id: int, limit: int = 50) -> list[AuditLog]: ...

    @abstractmethod
    def list_recent(self, limit: int = 50) -> list[AuditLog]: ...


class ReceiptRepository(ABC):
    @abstractmethod
    def create(self, receipt: Receipt) -> Receipt: ...

    @abstractmethod
    def get_by_id(self, receipt_id: int) -> Receipt | None: ...

    @abstractmethod
    def get_by_uuid(self, uuid: str) -> Receipt | None: ...

    @abstractmethod
    def list_by_bill(self, bill_id: int) -> list[Receipt]: ...

    @abstractmethod
    def delete(self, receipt_id: int) -> None: ...


class MFATOTPRepository(ABC):
    @abstractmethod
    def get_by_user_id(self, user_id: int) -> UserTOTP | None: ...

    @abstractmethod
    def create(self, totp: UserTOTP) -> UserTOTP: ...

    @abstractmethod
    def confirm(self, user_id: int) -> None: ...

    @abstractmethod
    def delete_by_user_id(self, user_id: int) -> None: ...


class RecoveryCodeRepository(ABC):
    @abstractmethod
    def create_batch(self, user_id: int, code_hashes: list[str]) -> None: ...

    @abstractmethod
    def list_unused_by_user(self, user_id: int) -> list[RecoveryCode]: ...

    @abstractmethod
    def mark_used(self, code_id: int) -> None: ...

    @abstractmethod
    def delete_all_by_user(self, user_id: int) -> None: ...


class PasskeyRepository(ABC):
    @abstractmethod
    def create(self, passkey: UserPasskey) -> UserPasskey: ...

    @abstractmethod
    def get_by_uuid(self, uuid: str) -> UserPasskey | None: ...

    @abstractmethod
    def get_by_credential_id(self, credential_id: str) -> UserPasskey | None: ...

    @abstractmethod
    def list_by_user(self, user_id: int) -> list[UserPasskey]: ...

    @abstractmethod
    def update_sign_count(self, passkey_id: int, sign_count: int) -> None: ...

    @abstractmethod
    def update_last_used(self, passkey_id: int) -> None: ...

    @abstractmethod
    def delete(self, passkey_id: int) -> None: ...
