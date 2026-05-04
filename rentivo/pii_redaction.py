"""Partial-mask redaction for PII values in audit logs and similar contexts.

NOT encryption. The mask is a one-way visual partial-disclosure: it preserves
enough of the value for an auditor to recognize "the email went to a gmail
address" or "the CPF starts with 123 ends with 89" without revealing the full
identifier. The masked form is short, idempotent (re-redacting a redacted
value is a no-op for typical inputs), and requires no key material.
"""

from __future__ import annotations

from enum import Enum

_PIX_PREFIX = 3
_PIX_SUFFIX = 2
_EMAIL_LOCAL_PREFIX = 2
_PIX_MIN_LEN = _PIX_PREFIX + _PIX_SUFFIX + 1  # need at least 1 hidden char
_EMAIL_LOCAL_MIN_LEN = _EMAIL_LOCAL_PREFIX + 1


class PIIKind(str, Enum):
    """Discriminator that selects the partial-mask shape for ``redact()``."""

    PIX = "pix"
    EMAIL = "email"


def redact(value: str, kind: PIIKind) -> str:
    """Return a partially-masked view of ``value`` suitable for audit logs.

    Empty / falsy input returns ``""`` so audit consumers can distinguish
    "value not set" from "value present but masked".
    """
    if not value:
        return ""
    if kind is PIIKind.PIX:
        return _mask_pix(value)
    if kind is PIIKind.EMAIL:
        return _mask_email(value)
    raise ValueError(f"Unknown PII kind: {kind}")


def _mask_pix(value: str) -> str:
    """First 3 chars + ``...`` + last 2 chars. Short values collapse to ``***``.

    Examples::

        12345678901      -> 123...01
        alice@pix.com    -> ali...om
        Alice            -> ***   (only 5 chars; can't hide anything)
    """
    if len(value) < _PIX_MIN_LEN:
        return "***"
    return f"{value[:_PIX_PREFIX]}...{value[-_PIX_SUFFIX:]}"


def _mask_email(value: str) -> str:
    """First 2 chars of local part + ``...@`` + full domain. Domain stays
    unredacted because the bulk of identification utility is in the local
    part. Local parts shorter than 3 chars collapse to ``***``. Values with
    no ``@`` fall back to the PIX mask.

    Examples::

        joe@gmail.com         -> jo...@gmail.com
        a@x.co                -> ***@x.co
        not-an-email          -> not...il   (PIX-mask fallback)
    """
    if "@" not in value:
        return _mask_pix(value)
    local, _, domain = value.partition("@")
    if len(local) < _EMAIL_LOCAL_MIN_LEN:
        return f"***@{domain}"
    return f"{local[:_EMAIL_LOCAL_PREFIX]}...@{domain}"
