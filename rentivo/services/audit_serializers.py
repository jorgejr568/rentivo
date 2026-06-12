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
from rentivo.models.receipt import Receipt
from rentivo.models.theme import Theme
from rentivo.models.user import User
from rentivo.pii_redaction import PIIKind, redact


def _dt(val: datetime | None) -> str | None:
    """Convert datetime to ISO string, or None."""
    if val is None:
        return None
    return val.isoformat()


def serialize_billing(billing: Billing) -> dict:
    """Serialize a Billing (with items) for audit state.

    PIX fields are partial-mask redacted (first 3 chars + ``...`` + last 2 chars).
    """
    return {
        "id": billing.id,
        "uuid": billing.uuid,
        "name": billing.name,
        "description": billing.description,
        "pix_key": redact(billing.pix_key or "", PIIKind.PIX),
        "pix_merchant_name": redact(billing.pix_merchant_name or "", PIIKind.PIX),
        "pix_merchant_city": redact(billing.pix_merchant_city or "", PIIKind.PIX),
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


def serialize_receipt(receipt: Receipt, *, bill_uuid: str, billing_uuid: str) -> dict:
    """Serialize a Receipt for audit state.

    ``bill_uuid`` / ``billing_uuid`` come from the calling context — the
    Receipt model only carries the numeric ``bill_id``. ``filename`` is stored
    as provided, matching the pre-refactor inline dicts in web/routes/bill.py.
    """
    return {
        "filename": receipt.filename,
        "content_type": receipt.content_type,
        "file_size": receipt.file_size,
        "bill_uuid": bill_uuid,
        "billing_uuid": billing_uuid,
    }


def serialize_user(user: User) -> dict:
    """Serialize a User for audit state.

    Excludes ``password_hash``. Email is partial-mask redacted via
    :func:`rentivo.pii_redaction.redact` with ``PIIKind.EMAIL`` — first 2 chars
    of local-part + ``...@`` + full domain (e.g. ``jo...@gmail.com``). PIX fields
    (``pix_key``, ``pix_merchant_name``, ``pix_merchant_city``) are also
    partial-mask redacted — first 3 chars + ``...`` + last 2 chars. Empty values
    redact to ``""``. The mask is one-way and key-less.
    """
    return {
        "id": user.id,
        "email": redact(user.email or "", PIIKind.EMAIL),
        "pix_key": redact(user.pix_key or "", PIIKind.PIX),
        "pix_merchant_name": redact(user.pix_merchant_name or "", PIIKind.PIX),
        "pix_merchant_city": redact(user.pix_merchant_city or "", PIIKind.PIX),
        "created_at": _dt(user.created_at),
    }


def serialize_organization(org: Organization) -> dict:
    """Serialize an Organization for audit state.

    PIX fields are partial-mask redacted (first 3 chars + ``...`` + last 2 chars).
    """
    return {
        "id": org.id,
        "uuid": org.uuid,
        "name": org.name,
        "created_by": org.created_by,
        "enforce_mfa": org.enforce_mfa,
        "pix_key": redact(org.pix_key or "", PIIKind.PIX),
        "pix_merchant_name": redact(org.pix_merchant_name or "", PIIKind.PIX),
        "pix_merchant_city": redact(org.pix_merchant_city or "", PIIKind.PIX),
        "created_at": _dt(org.created_at),
        "updated_at": _dt(org.updated_at),
    }


def serialize_invite(invite: Invite) -> dict:
    """Serialize an Invite for audit state.

    Email fields are partial-mask redacted via :func:`rentivo.pii_redaction.redact`
    with ``PIIKind.EMAIL`` (first 2 chars of local-part + ``...@`` + full domain).
    ``organization_name`` is dropped — the row already references the org by id,
    and the org's name is captured under the dedicated organization audit events
    via :func:`serialize_organization`.
    """
    return {
        "id": invite.id,
        "uuid": invite.uuid,
        "organization_id": invite.organization_id,
        "invited_user_id": invite.invited_user_id,
        "invited_email": redact(invite.invited_email or "", PIIKind.EMAIL),
        "invited_by_user_id": invite.invited_by_user_id,
        "invited_by_email": redact(invite.invited_by_email or "", PIIKind.EMAIL),
        "role": invite.role,
        "status": invite.status,
        "created_at": _dt(invite.created_at),
        "responded_at": _dt(invite.responded_at),
    }


def serialize_theme(theme: Theme) -> dict:
    """Serialize a Theme for audit state."""
    return {
        "uuid": theme.uuid,
        "owner_type": theme.owner_type,
        "owner_id": theme.owner_id,
        "name": theme.name,
        "header_font": theme.header_font,
        "text_font": theme.text_font,
        "primary": theme.primary,
        "primary_light": theme.primary_light,
        "secondary": theme.secondary,
        "secondary_dark": theme.secondary_dark,
        "text_color": theme.text_color,
        "text_contrast": theme.text_contrast,
    }


_DISALLOWED_KEY_PATTERNS = ("password", "token", "secret")
_DISALLOWED_KEY_PREFIXES = ("pix_merchant_",)
_DISALLOWED_KEYS_EXACT = {"pix_key"}


def _is_disallowed_key(key: str) -> bool:
    lower = key.lower()
    if lower in _DISALLOWED_KEYS_EXACT:
        return True
    if any(lower.startswith(p) for p in _DISALLOWED_KEY_PREFIXES):
        return True
    return any(pat in lower for pat in _DISALLOWED_KEY_PATTERNS)


def serialize_job_payload(payload: dict) -> dict:
    """Audit-safe view of a queued job's payload.

    For email.send: keeps ``event``, a partial-mask redaction of ``to_email``
    (e.g. ``jo...@gmail.com`` — first 2 chars of local + full domain) so
    reviewers can recognize the recipient domain without seeing the address,
    and a count of ctx keys, but drops every ctx value (templates can carry
    org names, IPs, reset URLs — none belong in audit rows). For s3.delete:
    keeps ``key`` (a ULID-only storage path; safe to log). For unknown job
    types we keep only a sorted index of top-level keys.
    """
    job_type = payload.get("job_type", "")
    if job_type == "email.send":
        return {
            "event": payload.get("event"),
            "to_email": redact(payload.get("to_email", "") or "", PIIKind.EMAIL),
            "ctx_keys_count": len(payload.get("ctx") or {}),
        }
    if job_type == "s3.delete":
        return {"key": payload.get("key", "")}
    return {
        "job_type": job_type,
        "keys": sorted(k for k in payload.keys() if not _is_disallowed_key(k)),
    }
