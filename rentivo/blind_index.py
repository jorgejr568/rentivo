"""Blind-index hash for email lookups.

`users.email` is encrypted at rest with the EncryptionBackend (KMS or base64),
so `WHERE email = ?` no longer works — KMS ciphertext is non-deterministic.
This module computes a deterministic HMAC-SHA256 of the normalized email so we
can index and equality-match without ever scanning ciphertext.

Key material derives from ``settings.secret_key`` (env var ``RENTIVO_SECRET_KEY``)
via SHA-256 over a fixed domain-prefix. Rotating ``RENTIVO_SECRET_KEY``
invalidates every existing ``users.email_hash``; run
``make backfill-encryption-reset-blind-index`` afterwards to repopulate.

Normalisation: ``email.strip().lower()`` — matches the de-facto user
expectation that "Alice@Example.com" and "alice@example.com" are the same
account.
"""

from __future__ import annotations

import hashlib
import hmac

from rentivo.settings import settings

_cached_key: bytes | None = None


def _load_key() -> bytes:
    """Return the 32-byte HMAC key. Caches on first call."""
    global _cached_key
    if _cached_key is not None:
        return _cached_key
    _cached_key = hashlib.sha256(b"rentivo:email-blind-index:v1:" + settings.secret_key.encode()).digest()
    return _cached_key


def compute_email_hash(email: str) -> str:
    """Return the hex HMAC-SHA256 of the normalized email.

    Empty or whitespace-only input returns ``""``.
    """
    normalized = email.strip().lower()
    if not normalized:
        return ""
    return hmac.new(_load_key(), normalized.encode("utf-8"), hashlib.sha256).hexdigest()
