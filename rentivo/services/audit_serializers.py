"""Serializers that convert models to dicts suitable for audit log state fields.

Sensitive fields like password_hash are explicitly excluded.
Datetime fields are converted to ISO 8601 strings for JSON compatibility.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime

from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.invite import Invite
from rentivo.models.organization import Organization
from rentivo.models.user import User
from rentivo.settings import settings


def _dt(val: datetime | None) -> str | None:
    """Convert datetime to ISO string, or None."""
    if val is None:
        return None
    return val.isoformat()


def serialize_billing(billing: Billing) -> dict:
    """Serialize a Billing (with items) for audit state. PIX fields are redacted to presence booleans."""
    return {
        "id": billing.id,
        "uuid": billing.uuid,
        "name": billing.name,
        "description": billing.description,
        "pix_key_set": bool(billing.pix_key),
        "pix_merchant_name_set": bool(billing.pix_merchant_name),
        "pix_merchant_city_set": bool(billing.pix_merchant_city),
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
        "status": bill.status,
        "status_updated_at": _dt(bill.status_updated_at),
        "created_at": _dt(bill.created_at),
    }


def serialize_user(user: User) -> dict:
    """Serialize a User for audit state.

    Excludes ``password_hash``. PIX fields (``pix_key``, ``pix_merchant_name``,
    ``pix_merchant_city``) are redacted to presence booleans (``*_set``) so the
    audit trail records when PIX was configured / cleared without storing the
    plaintext PIX value.
    """
    return {
        "id": user.id,
        "email": user.email,
        "pix_key_set": bool(user.pix_key),
        "pix_merchant_name_set": bool(user.pix_merchant_name),
        "pix_merchant_city_set": bool(user.pix_merchant_city),
        "created_at": _dt(user.created_at),
    }


def serialize_organization(org: Organization) -> dict:
    """Serialize an Organization for audit state. PIX fields are redacted to presence booleans."""
    return {
        "id": org.id,
        "uuid": org.uuid,
        "name": org.name,
        "created_by": org.created_by,
        "enforce_mfa": org.enforce_mfa,
        "pix_key_set": bool(org.pix_key),
        "pix_merchant_name_set": bool(org.pix_merchant_name),
        "pix_merchant_city_set": bool(org.pix_merchant_city),
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
        "invited_email": invite.invited_email,
        "invited_by_user_id": invite.invited_by_user_id,
        "invited_by_email": invite.invited_by_email,
        "role": invite.role,
        "status": invite.status,
        "created_at": _dt(invite.created_at),
        "responded_at": _dt(invite.responded_at),
    }


_DISALLOWED_KEY_PATTERNS = ("password", "token", "secret")
_DISALLOWED_KEY_PREFIXES = ("pix_merchant_",)
_DISALLOWED_KEYS_EXACT = {"pix_key"}


def _hash_email(email: str) -> str:
    """HMAC-SHA256 of ``email`` keyed by ``settings.secret_key``, truncated to
    16 hex chars. Empty / falsy input returns ``""``.

    Used to keep ``to_email`` correlatable across audit rows (same recipient
    yields the same hash) without storing the plaintext address. Rotating
    ``secret_key`` invalidates correlation but does not corrupt audit history —
    new rows simply don't correlate to old ones.
    """
    if not email:
        return ""
    digest = hmac.new(
        settings.get_secret_key().encode("utf-8"),
        email.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:16]


def _is_disallowed_key(key: str) -> bool:
    lower = key.lower()
    if lower in _DISALLOWED_KEYS_EXACT:
        return True
    if any(lower.startswith(p) for p in _DISALLOWED_KEY_PREFIXES):
        return True
    return any(pat in lower for pat in _DISALLOWED_KEY_PATTERNS)


def serialize_job_payload(payload: dict) -> dict:
    """Audit-safe view of a queued job's payload.

    For email.send: keeps ``event``, an HMAC hash of ``to_email`` (so reviewers
    can correlate "same recipient" across audit rows without seeing the address),
    and a count of ctx keys, but drops every ctx value (templates can carry org
    names, IPs, reset URLs — none belong in audit rows). For s3.delete: keeps
    ``key`` (a ULID-only storage path; safe to log). For unknown job types we
    keep only a sorted index of top-level keys.
    """
    job_type = payload.get("job_type", "")
    if job_type == "email.send":
        return {
            "event": payload.get("event"),
            "to_email_hash": _hash_email(payload.get("to_email", "") or ""),
            "ctx_keys_count": len(payload.get("ctx") or {}),
        }
    if job_type == "s3.delete":
        return {"key": payload.get("key", "")}
    return {
        "job_type": job_type,
        "keys": sorted(k for k in payload.keys() if not _is_disallowed_key(k)),
    }
