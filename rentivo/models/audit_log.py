from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditEventType:
    """String constants for all audit event types."""

    # User events
    USER_LOGIN = "user.login"
    USER_LOGIN_FAILED = "user.login_failed"
    USER_SIGNUP = "user.signup"
    USER_CREATE = "user.create"
    USER_CHANGE_PASSWORD = "user.change_password"
    USER_LOGOUT = "user.logout"

    # Billing events
    BILLING_CREATE = "billing.create"
    BILLING_UPDATE = "billing.update"
    BILLING_DELETE = "billing.delete"
    BILLING_TRANSFER = "billing.transfer"

    # Bill events
    BILL_CREATE = "bill.create"
    BILL_UPDATE = "bill.update"
    BILL_DELETE = "bill.delete"
    BILL_TOGGLE_PAID = "bill.toggle_paid"
    BILL_REGENERATE_PDF = "bill.regenerate_pdf"

    # Receipt events
    RECEIPT_UPLOAD = "receipt.upload"
    RECEIPT_DELETE = "receipt.delete"

    # Organization events
    ORGANIZATION_CREATE = "organization.create"
    ORGANIZATION_UPDATE = "organization.update"
    ORGANIZATION_DELETE = "organization.delete"
    ORGANIZATION_ADD_MEMBER = "organization.add_member"
    ORGANIZATION_REMOVE_MEMBER = "organization.remove_member"
    ORGANIZATION_UPDATE_MEMBER_ROLE = "organization.update_member_role"

    # Invite events
    INVITE_SEND = "invite.send"
    INVITE_ACCEPT = "invite.accept"
    INVITE_DECLINE = "invite.decline"

    # MFA events
    MFA_TOTP_ENABLED = "mfa.totp_enabled"
    MFA_TOTP_DISABLED = "mfa.totp_disabled"
    MFA_CHALLENGE_ISSUED = "mfa.challenge_issued"
    MFA_VERIFY_SUCCESS = "mfa.verify_success"
    MFA_VERIFY_FAILED = "mfa.verify_failed"
    MFA_RECOVERY_USED = "mfa.recovery_used"
    MFA_RECOVERY_REGENERATED = "mfa.recovery_regenerated"
    MFA_PASSKEY_REGISTERED = "mfa.passkey_registered"
    MFA_PASSKEY_DELETED = "mfa.passkey_deleted"
    MFA_PASSKEY_USED = "mfa.passkey_used"
    ORGANIZATION_UPDATE_MFA = "organization.update_mfa"


class AuditLog(BaseModel):
    id: int | None = None
    uuid: str = ""
    event_type: str
    actor_id: int | None = None
    actor_username: str = ""
    source: str = ""  # 'web' or 'cli'
    entity_type: str = ""
    entity_id: int | None = None
    entity_uuid: str = ""
    previous_state: dict | None = None  # JSON (None for creates)
    new_state: dict | None = None  # JSON (None for deletes)
    metadata: dict = {}
    created_at: datetime | None = None
