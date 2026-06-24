from abc import ABC, abstractmethod
from datetime import datetime

from rentivo.models.audit_log import AuditLog
from rentivo.models.bill import Bill, BillSummary
from rentivo.models.billing import Billing
from rentivo.models.billing_attachment import BillingAttachment
from rentivo.models.communication import Communication, CommunicationTemplate
from rentivo.models.invite import Invite
from rentivo.models.known_device import KnownDevice
from rentivo.models.mfa import RecoveryCode, UserPasskey, UserTOTP
from rentivo.models.organization import Organization, OrganizationMember
from rentivo.models.password_reset_token import PasswordResetToken
from rentivo.models.receipt import Receipt
from rentivo.models.recipient import Recipient
from rentivo.models.theme import Theme
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
    def list_summaries(self, billing_ids: list[int]) -> list[BillSummary]:
        """All (non-deleted) bills for the given billings as lightweight summaries,
        ordered by billing_id then newest reference_month first. Lets callers derive
        both the latest bill per billing and year-to-date rollups from one query."""
        ...

    @abstractmethod
    def update(self, bill: Bill) -> Bill: ...

    @abstractmethod
    def update_pdf_path(self, bill_id: int, pdf_path: str) -> None: ...

    @abstractmethod
    def update_status(self, bill_id: int, status: str, status_updated_at: datetime) -> None: ...

    @abstractmethod
    def update_pdf_render_status(self, bill_id: int, status: str | None) -> None: ...

    @abstractmethod
    def update_pix_linkage(
        self,
        bill_id: int,
        *,
        provider: str | None = None,
        charge_id: str | None = None,
        txid: str | None = None,
        e2eid: str | None = None,
    ) -> None:
        """Persist dynamic-PIX (PSP) linkage columns on a bill.

        Only non-``None`` arguments are written, so a webhook can fill in the
        ``e2eid`` it learns at settlement without clobbering the
        ``provider``/``charge_id`` set at charge-creation time."""
        ...

    @abstractmethod
    def delete(self, bill_id: int) -> None: ...


class UserRepository(ABC):
    @abstractmethod
    def create(self, user: User) -> User: ...

    @abstractmethod
    def get_by_id(self, user_id: int) -> User | None: ...

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def list_all(self) -> list[User]: ...

    @abstractmethod
    def update_password_hash(self, user_id: int, password_hash: str) -> None: ...

    @abstractmethod
    def update_pix(self, user_id: int, pix_key: str, pix_merchant_name: str, pix_merchant_city: str) -> None: ...


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

    @abstractmethod
    def update_sort_orders(self, updates: list[tuple[int, int]]) -> None: ...


class BillingAttachmentRepository(ABC):
    @abstractmethod
    def create(self, attachment: BillingAttachment) -> BillingAttachment: ...

    @abstractmethod
    def get_by_id(self, attachment_id: int) -> BillingAttachment | None: ...

    @abstractmethod
    def get_by_uuid(self, uuid: str) -> BillingAttachment | None: ...

    @abstractmethod
    def list_by_billing(self, billing_id: int) -> list[BillingAttachment]: ...

    @abstractmethod
    def delete(self, attachment_id: int) -> None: ...


class RecipientRepository(ABC):
    @abstractmethod
    def list_by_billing(self, billing_id: int) -> list[Recipient]: ...

    @abstractmethod
    def get_by_uuid(self, uuid: str) -> Recipient | None: ...

    @abstractmethod
    def replace_for_billing(self, billing_id: int, recipients: list[Recipient]) -> None: ...


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


class ThemeRepository(ABC):
    @abstractmethod
    def create(self, theme: Theme) -> Theme: ...

    @abstractmethod
    def get_by_id(self, theme_id: int) -> Theme | None: ...

    @abstractmethod
    def get_by_uuid(self, uuid: str) -> Theme | None: ...

    @abstractmethod
    def get_by_owner(self, owner_type: str, owner_id: int) -> Theme | None: ...

    @abstractmethod
    def update(self, theme: Theme) -> Theme: ...

    @abstractmethod
    def delete(self, theme_id: int) -> None: ...


class PasswordResetTokenRepository(ABC):
    @abstractmethod
    def create(self, token: PasswordResetToken) -> PasswordResetToken: ...

    @abstractmethod
    def get_by_hash(self, token_hash: str) -> PasswordResetToken | None: ...

    @abstractmethod
    def mark_used(self, token_id: int) -> None: ...

    @abstractmethod
    def invalidate_all_for_user(self, user_id: int) -> None: ...


class KnownDeviceRepository(ABC):
    @abstractmethod
    def get(self, user_id: int, device_hash: str) -> KnownDevice | None: ...

    @abstractmethod
    def upsert(self, device: KnownDevice) -> KnownDevice: ...


class CommunicationTemplateRepository(ABC):
    @abstractmethod
    def get(self, owner_type: str, owner_id: int, comm_type: str) -> CommunicationTemplate | None: ...

    @abstractmethod
    def upsert(self, template: CommunicationTemplate) -> CommunicationTemplate: ...


class CommunicationRepository(ABC):
    @abstractmethod
    def create(self, communication: Communication) -> Communication: ...

    @abstractmethod
    def get_by_id(self, communication_id: int) -> Communication | None: ...

    @abstractmethod
    def get_by_uuid(self, uuid: str) -> Communication | None: ...

    @abstractmethod
    def list_by_bill(self, bill_id: int) -> list[Communication]: ...

    @abstractmethod
    def set_job_ulid(self, communication_id: int, job_ulid: str) -> None: ...

    @abstractmethod
    def mark_sent(self, communication_id: int, sent_at: datetime) -> None: ...

    @abstractmethod
    def mark_failed(self, communication_id: int, error: str) -> None: ...


class PixWebhookEventRepository(ABC):
    """Idempotency / replay ledger for inbound PSP payment webhooks (REN-25)."""

    @abstractmethod
    def record_if_new(
        self,
        *,
        provider: str,
        event_id: str,
        event_type: str,
        status: str,
        charge_id: str | None = None,
        external_reference: str | None = None,
        e2eid: str | None = None,
        bill_id: int | None = None,
    ) -> bool:
        """Record a webhook delivery, returning ``True`` only on first sight.

        Inserts ``(provider, event_id)`` with ``ON CONFLICT DO NOTHING``
        semantics. A duplicate delivery (replay) returns ``False`` so the
        caller can ack ``200`` and stop without re-running the side effect."""
        ...

    @abstractmethod
    def set_bill_id(self, *, provider: str, event_id: str, bill_id: int) -> None:
        """Backfill the resolved ``bill_id`` on an already-recorded event."""
        ...
