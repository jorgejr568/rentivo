from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor

import structlog

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None  # type: ignore[assignment]

from rentivo.encryption.base import EncryptionBackend
from rentivo.observability import traced

logger = structlog.get_logger(__name__)

_PREFIX = "enc:v1:"
_BASE64_PREFIX = "b64:v1:"  # transitional read-compat: see decrypt()
_DECRYPT_MANY_MAX_WORKERS = 16


class KMSBackend(EncryptionBackend):
    """AWS KMS direct-encryption backend.

    Ciphertext format: ``enc:v1:<base64(KMS CiphertextBlob)>``.

    Direct KMS (rather than envelope encryption) is used because the values are
    small (PIX keys, merchant names, TOTP secrets — all well under KMS's 4 KB
    plaintext limit) and the read-volume profile does not justify the extra
    moving parts. If read volume grows, a future v2 ciphertext format can layer
    in per-row data-encryption keys with a local cache.
    """

    def __init__(
        self,
        key_id: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        endpoint_url: str = "",
    ) -> None:
        if boto3 is None:
            raise ImportError(
                "boto3 is required for KMS encryption. Install it with: pip install rentivo[s3] "
                "(the s3 extras group also provides the boto3 client used for KMS)."
            )
        self.key_id = key_id

        client_kwargs: dict = {
            "service_name": "kms",
            "region_name": region,
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
        }
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        self.client = boto3.client(**client_kwargs)

    @traced("kms.encrypt")
    def encrypt(self, plaintext: str) -> str:
        if plaintext == "":
            return ""
        if self.is_encrypted(plaintext):
            return plaintext
        response = self.client.encrypt(
            KeyId=self.key_id,
            Plaintext=plaintext.encode("utf-8"),
        )
        blob: bytes = response["CiphertextBlob"]
        encoded = base64.b64encode(blob).decode("ascii")
        logger.debug("encryption_encrypted", backend="kms", bytes=len(blob))
        return _PREFIX + encoded

    @traced("kms.decrypt")
    def decrypt(self, value: str) -> str:
        if value == "":
            return ""
        if value.startswith(_BASE64_PREFIX):
            # Transitional: a row written under Base64Backend before the cutover.
            # Decode locally without calling KMS so reads stay correct until the
            # backfill rewrites the row as enc:v1.
            return base64.b64decode(value[len(_BASE64_PREFIX) :]).decode("utf-8")
        if not self.is_encrypted(value):
            return value
        encoded = value[len(_PREFIX) :]
        blob = base64.b64decode(encoded)
        response = self.client.decrypt(CiphertextBlob=blob, KeyId=self.key_id)
        plaintext: bytes = response["Plaintext"]
        logger.debug("encryption_decrypted", backend="kms", bytes=len(plaintext))
        return plaintext.decode("utf-8")

    def is_encrypted(self, value: str) -> bool:
        return value.startswith(_PREFIX)

    @traced("kms.decrypt_many")
    def decrypt_many(self, values: list[str]) -> list[str]:
        if not values:
            return []
        # Boto3 KMS clients are thread-safe; fan out the per-value Decrypt RTTs
        # so a list page with N×M encrypted columns finishes in ~max RTT
        # instead of N×M × RTT.
        max_workers = min(_DECRYPT_MANY_MAX_WORKERS, len(values))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            return list(pool.map(self.decrypt, values))
