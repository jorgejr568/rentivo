from abc import ABC, abstractmethod
from datetime import datetime

from rentivo.models.api_key import APIKey, APIKeyGrant
from rentivo.models.audit_log import AuditLog
from rentivo.models.auth_challenge import AuthChallenge
from rentivo.models.bill import Bill, BillSummary
from rentivo.models.billing import Billing
from rentivo.models.billing_attachment import BillingAttachment
from rentivo.models.communication import Communication, CommunicationTemplate
from rentivo.models.expense import Expense
from rentivo.models.invite import Invite
from rentivo.models.known_device import KnownDevice
from rentivo.models.mfa import MFAFactorRemovalResult, RecoveryCode, UserPasskey, UserTOTP
from rentivo.models.organization import Organization, OrganizationMember
from rentivo.models.password_reset_token import PasswordResetToken
from rentivo.models.receipt import Receipt
from rentivo.models.recipient import Recipient
from rentivo.models.theme import Theme
from rentivo.models.user import User


class UserAlreadyRegisteredError(ValueError):
    pass


class APIKeyPersistenceError(RuntimeError):
    """Sanitized failure that is safe to propagate through request telemetry."""


class AuthChallengePersistenceError(RuntimeError):
    """Sanitized failure that is safe to propagate through request telemetry."""


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
    def update_recibo_pdf_path(self, bill_id: int, recibo_pdf_path: str | None) -> None: ...

    @abstractmethod
    def update_status(self, bill_id: int, status: str, status_updated_at: datetime) -> None: ...

    @abstractmethod
    def update_pdf_render_status(self, bill_id: int, status: str | None) -> None: ...

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
    def change_password_and_revoke_other_login_tokens(
        self,
        user_id: int,
        password_hash: str,
        current_key_uuid: str,
    ) -> int: ...

    @abstractmethod
    def delete(self, user_id: int) -> bool: ...

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


class ExpenseRepository(ABC):
    @abstractmethod
    def create(self, expense: Expense) -> Expense: ...

    @abstractmethod
    def get_by_uuid(self, uuid: str) -> Expense | None: ...

    @abstractmethod
    def list_by_billing(self, billing_id: int) -> list[Expense]: ...

    @abstractmethod
    def delete(self, expense_id: int) -> None: ...

    @abstractmethod
    def total_for_billings(self, billing_ids: list[int]) -> int:
        """Sum of ``amount`` (centavos) over all non-deleted expenses for the
        given billings. Returns 0 for an empty id list."""
        ...


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
    def mark_used(self, code_id: int) -> bool: ...

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
    def update_sign_count(
        self,
        passkey_id: int,
        expected_sign_count: int,
        expected_last_used_at: datetime | None,
        new_sign_count: int,
    ) -> bool: ...

    @abstractmethod
    def update_last_used(self, passkey_id: int) -> None: ...

    @abstractmethod
    def delete(self, passkey_id: int) -> None: ...


class MFAFactorRepository(ABC):
    @abstractmethod
    def remove_totp_and_revoke_logins(self, user_id: int) -> MFAFactorRemovalResult: ...

    @abstractmethod
    def remove_passkey_and_revoke_logins(
        self,
        passkey_uuid: str,
        user_id: int,
    ) -> MFAFactorRemovalResult: ...


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

    @abstractmethod
    def complete_password_reset(
        self,
        *,
        token_id: int,
        user_id: int,
        password_hash: str,
        completed_at: datetime,
    ) -> bool: ...


class AuthRateLimitRepository(ABC):
    @abstractmethod
    def reserve(
        self,
        *,
        action: str,
        identity_hash: bytes,
        limit: int,
        window_seconds: int,
        now: datetime,
    ) -> bool: ...

    @abstractmethod
    def clear(self, *, action: str, identity_hash: bytes) -> None: ...

    @abstractmethod
    def delete_expired(self, *, cutoff: datetime, limit: int) -> int: ...


class KnownDeviceRepository(ABC):
    @abstractmethod
    def get(self, user_id: int, device_hash: str) -> KnownDevice | None: ...

    @abstractmethod
    def upsert(self, device: KnownDevice) -> KnownDevice: ...


class APIKeyRepository(ABC):
    @abstractmethod
    def create(
        self,
        api_key: APIKey,
        *,
        scopes: frozenset[str],
        grants: tuple[APIKeyGrant, ...],
    ) -> APIKey: ...

    @abstractmethod
    def get_by_secret_hash(self, secret_hash: bytes) -> APIKey | None: ...

    @abstractmethod
    def get_integration_by_uuid(self, user_id: int, uuid: str) -> APIKey | None: ...

    @abstractmethod
    def list_integrations(self, user_id: int) -> list[APIKey]: ...

    @abstractmethod
    def update_integration(
        self,
        api_key: APIKey,
        *,
        scopes: frozenset[str],
        grants: tuple[APIKeyGrant, ...],
    ) -> APIKey | None: ...

    @abstractmethod
    def delete_login_token(self, api_key_id: int) -> bool: ...

    @abstractmethod
    def revoke_integration(self, user_id: int, uuid: str, revoked_at: datetime) -> bool: ...

    @abstractmethod
    def revoke_other_login_tokens(self, user_id: int, current_key_uuid: str) -> int: ...

    @abstractmethod
    def revoke_all_login_tokens(self, user_id: int) -> int: ...

    @abstractmethod
    def delete_expired_login_tokens(self, cutoff: datetime) -> int: ...

    @abstractmethod
    def touch_last_used(self, api_key_id: int, used_at: datetime, cutoff: datetime) -> bool: ...


class AuthChallengeRepository(ABC):
    @abstractmethod
    def create(self, challenge: AuthChallenge) -> AuthChallenge: ...

    @abstractmethod
    def get_by_uuid(self, uuid: str) -> AuthChallenge | None: ...

    @abstractmethod
    def increment_failures(self, uuid: str, phase: str, failed_at: datetime) -> bool: ...

    @abstractmethod
    def set_webauthn_challenge(
        self,
        uuid: str,
        phase: str,
        webauthn_challenge: bytes,
        updated_at: datetime,
    ) -> bool: ...

    @abstractmethod
    def consume(self, uuid: str, phase: str, consumed_at: datetime) -> bool: ...


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
