"""Partial-mask redaction for PII values in audit logs and similar contexts.

NOT encryption. The mask is a one-way visual partial-disclosure: it preserves
enough of the value for an auditor to recognize "the email went to a gmail
address" or "the CPF starts with 123 ends with 89" without revealing the full
identifier. The masked form is short, idempotent (re-redacting a redacted
value is a no-op for typical inputs), and requires no key material.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, overload

_PIX_PREFIX = 3
_PIX_SUFFIX = 2
_EMAIL_LOCAL_PREFIX = 2
_PIX_MIN_LEN = _PIX_PREFIX + _PIX_SUFFIX + 1  # need at least 1 hidden char
_EMAIL_LOCAL_MIN_LEN = _EMAIL_LOCAL_PREFIX + 1


class PIIKind(str, Enum):
    """Discriminator that selects the partial-mask shape for ``redact()``."""

    PIX = "pix"
    EMAIL = "email"


_CREDENTIAL_FIELDS = frozenset(
    {
        "accesstoken",
        "apikey",
        "apikeyhash",
        "apikeysecret",
        "assertion",
        "attestationobject",
        "authenticationtoken",
        "accesscredential",
        "authenticatordata",
        "authorization",
        "authorizationcode",
        "bearertoken",
        "challenge",
        "challengehash",
        "challengetoken",
        "clientsecret",
        "clientdatajson",
        "cookie",
        "credential",
        "credentialhash",
        "credentialsecret",
        "csrf",
        "csrftoken",
        "currentpassword",
        "codeverifier",
        "logintoken",
        "mfacode",
        "newpassword",
        "nonce",
        "noncehash",
        "idtoken",
        "oauthcode",
        "oauthtoken",
        "oldpassword",
        "password",
        "passwordconfirm",
        "passwordconfirmation",
        "passwordhash",
        "passwordresettoken",
        "rawid",
        "recoverycode",
        "recoverycodes",
        "refreshtoken",
        "resettoken",
        "secret",
        "secrethash",
        "secretkey",
        "sessiontoken",
        "setcookie",
        "signature",
        "totp",
        "totpcode",
        "totpsecret",
        "userhandle",
        "verificationtoken",
        "awssecretaccesskey",
    }
)
_REDACTED = "[REDACTED]"
_API_KEY_PATTERN = re.compile(r"rntv-v1-[A-Za-z0-9_-]{12,}")
_BEARER_PATTERN = re.compile(r"(?i)(\bbearer\s+)(?P<value>\[REDACTED\]|[^\s,;\"')\]}]+)")
_COOKIE_HEADER_PATTERN = re.compile(r"(?i)(\b(?:set-cookie|cookie)\s*:\s*)[^\r\n]+")
_CREDENTIAL_ASSIGNMENT_PATTERN = re.compile(
    r"(?P<prefix>\b(?P<field>[A-Za-z][A-Za-z0-9_.-]{1,63})\s*[:=]\s*)"
    r"(?P<value>\[REDACTED\]|\"[^\"]*\"|'[^']*'|[^\s,;\"')\]}]+)"
)
_HEADER_FIELDS = frozenset({"authorization", "cookie", "setcookie"})


@overload
def redact(value: str, kind: PIIKind) -> str: ...


@overload
def redact(value: Any, kind: None = None) -> Any: ...


def redact(value: Any, kind: PIIKind | None = None) -> Any:
    """Return a partially-masked view of ``value`` suitable for audit logs.

    Empty / falsy input returns ``""`` so audit consumers can distinguish
    "value not set" from "value present but masked".
    """
    if kind is None:
        return _redact_credentials(value)
    if not value:
        return ""
    if kind is PIIKind.PIX:
        return _mask_pix(value)
    if kind is PIIKind.EMAIL:
        return _mask_email(value)
    raise ValueError(f"Unknown PII kind: {kind}")


def _redact_credentials(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _REDACTED if _normalize_field(key) in _CREDENTIAL_FIELDS else _redact_credentials(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_credentials(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_credentials(item) for item in value)
    if isinstance(value, str):
        if _API_KEY_PATTERN.search(value):
            return _REDACTED
        return _redact_credential_string(value)
    return value


def _redact_credential_string(value: str) -> str:
    value = _COOKIE_HEADER_PATTERN.sub(lambda match: f"{match.group(1)}{_REDACTED}", value)
    value = _BEARER_PATTERN.sub(lambda match: f"{match.group(1)}{_REDACTED}", value)

    def replace_assignment(match: re.Match[str]) -> str:
        field = _normalize_field(match.group("field"))
        assigned_value = match.group("value")
        if field not in _CREDENTIAL_FIELDS or field in _HEADER_FIELDS:
            return f"{match.group('prefix')}{_redact_credential_string(assigned_value)}"
        if assigned_value == _REDACTED:
            return match.group(0)
        return f"{match.group('prefix')}{_REDACTED}"

    return _CREDENTIAL_ASSIGNMENT_PATTERN.sub(replace_assignment, value)


def _normalize_field(field: Any) -> str:
    return "".join(character for character in str(field).casefold() if character.isalnum())


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
