"""Serializers that convert models to dicts suitable for audit log state fields.

Sensitive fields like password_hash are explicitly excluded.
Datetime fields are converted to ISO 8601 strings for JSON compatibility.
"""

from __future__ import annotations

from datetime import datetime

from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.invite import Invite
from rentivo.models.organization import Organization
from rentivo.models.user import User


def _dt(val: datetime | None) -> str | None:
    """Convert datetime to ISO string, or None."""
    if val is None:
        return None
    return val.isoformat()


def serialize_billing(billing: Billing) -> dict:
    """Serialize a Billing (with items) for audit state."""
    return {
        "id": billing.id,
        "uuid": billing.uuid,
        "name": billing.name,
        "description": billing.description,
        "pix_key": billing.pix_key,
        "owner_type": billing.owner_type,
        "owner_id": billing.owner_id,
        "items": [
            {
                "id": item.id,
                "description": item.description,
                "amount": item.amount,
                "item_type": item.item_type.value if hasattr(item.item_type, "value") else str(item.item_type),
                "sort_order": item.sort_order,
            }
            for item in billing.items
        ],
        "created_at": _dt(billing.created_at),
        "updated_at": _dt(billing.updated_at),
    }


def serialize_bill(bill: Bill) -> dict:
    """Serialize a Bill (with line_items) for audit state."""
    return {
        "id": bill.id,
        "uuid": bill.uuid,
        "billing_id": bill.billing_id,
        "reference_month": bill.reference_month,
        "total_amount": bill.total_amount,
        "line_items": [
            {
                "id": item.id,
                "description": item.description,
                "amount": item.amount,
                "item_type": item.item_type.value if hasattr(item.item_type, "value") else str(item.item_type),
                "sort_order": item.sort_order,
            }
            for item in bill.line_items
        ],
        "pdf_path": bill.pdf_path,
        "notes": bill.notes,
        "due_date": bill.due_date,
        "paid_at": _dt(bill.paid_at),
        "created_at": _dt(bill.created_at),
    }


def serialize_user(user: User) -> dict:
    """Serialize a User for audit state. Excludes password_hash."""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": _dt(user.created_at),
    }


def serialize_organization(org: Organization) -> dict:
    """Serialize an Organization for audit state."""
    return {
        "id": org.id,
        "uuid": org.uuid,
        "name": org.name,
        "created_by": org.created_by,
        "enforce_mfa": org.enforce_mfa,
        "created_at": _dt(org.created_at),
        "updated_at": _dt(org.updated_at),
    }


def serialize_invite(invite: Invite) -> dict:
    """Serialize an Invite for audit state."""
    return {
        "id": invite.id,
        "uuid": invite.uuid,
        "organization_id": invite.organization_id,
        "organization_name": invite.organization_name,
        "invited_user_id": invite.invited_user_id,
        "invited_username": invite.invited_username,
        "invited_by_user_id": invite.invited_by_user_id,
        "invited_by_username": invite.invited_by_username,
        "role": invite.role,
        "status": invite.status,
        "created_at": _dt(invite.created_at),
        "responded_at": _dt(invite.responded_at),
    }
