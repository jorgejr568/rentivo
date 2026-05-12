"""Blind-index hash for email lookups.

`users.email` is encrypted at rest with the EncryptionBackend (KMS or base64),
so `WHERE email = ?` no longer works — KMS ciphertext is non-deterministic.
This module computes a deterministic HMAC-SHA256 of the normalized email so we
can index and equality-match without ever scanning ciphertext.

Key material:

- **KMS mode:** the 32-byte HMAC key is generated once at provisioning, sealed
  under the existing KMS key with ``kms.Encrypt``, and the resulting blob is
  stored in ``RENTIVO_EMAIL_BLIND_INDEX_KEY_CIPHERTEXT``. At first use the
  module calls ``kms.Decrypt`` once and caches the plaintext key in memory.
- **base64 mode:** for local dev the key derives from ``secret_key`` (which is
  already required). No KMS dependency in this path.

Normalisation: ``email.strip().lower()``. Matches the de-facto user expectation
that "Alice@Example.com" and "alice@example.com" are the same account.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from rentivo.settings import settings

_cached_key: bytes | None = None


def _get_kms_client():  # pragma: no cover - exercised via stub in tests
    import boto3

    kwargs: dict = {
        "region_name": settings.kms_region,
    }
    if settings.kms_access_key_id:
        kwargs["aws_access_key_id"] = settings.kms_access_key_id
    if settings.kms_secret_access_key:
        kwargs["aws_secret_access_key"] = settings.kms_secret_access_key
    if settings.kms_endpoint_url:
        kwargs["endpoint_url"] = settings.kms_endpoint_url
    return boto3.client("kms", **kwargs)


def _load_key() -> bytes:
    """Return the 32-byte HMAC key. Caches on first call."""
    global _cached_key
    if _cached_key is not None:
        return _cached_key

    if settings.encryption_backend == "kms":
        if not settings.email_blind_index_key_ciphertext:
            raise RuntimeError(
                "RENTIVO_EMAIL_BLIND_INDEX_KEY_CIPHERTEXT is required when RENTIVO_ENCRYPTION_BACKEND=kms"
            )
        client = _get_kms_client()
        response = client.decrypt(
            CiphertextBlob=base64.b64decode(settings.email_blind_index_key_ciphertext),
            KeyId=settings.kms_key_id,
        )
        _cached_key = response["Plaintext"]
    else:
        # base64 / dev mode: derive deterministically from secret_key.
        _cached_key = hashlib.sha256(b"rentivo:email-blind-index:v1:" + settings.secret_key.encode()).digest()

    return _cached_key


def compute_email_hash(email: str) -> str:
    """Return the hex HMAC-SHA256 of the normalized email. Empty or whitespace-only input → ``""``."""
    normalized = email.strip().lower()
    if not normalized:
        return ""
    return hmac.new(_load_key(), normalized.encode("utf-8"), hashlib.sha256).hexdigest()
