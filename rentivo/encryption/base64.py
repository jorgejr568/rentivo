from __future__ import annotations

import base64 as _b64

import structlog

from rentivo.encryption.base import EncryptionBackend

logger = structlog.get_logger(__name__)

_PREFIX = "b64:v1:"


class Base64Backend(EncryptionBackend):
    """Local-only obfuscation backend for development and tests.

    NOT encryption — base64 is reversible by anyone who can read the column.
    Its job is to give every environment the same "stored value differs from
    plaintext" contract as KMSBackend, so callers can never accidentally rely
    on ``column == plaintext`` working in dev but breaking in prod.

    Ciphertext format: ``b64:v1:<base64(plaintext)>``.
    """

    def encrypt(self, plaintext: str) -> str:
        if plaintext == "":
            return ""
        if self.is_encrypted(plaintext):
            return plaintext
        encoded = _b64.b64encode(plaintext.encode("utf-8")).decode("ascii")
        logger.debug("encryption_encoded", backend="base64", bytes=len(plaintext))
        return _PREFIX + encoded

    def decrypt(self, value: str) -> str:
        if value == "":
            return ""
        if not self.is_encrypted(value):
            return value
        encoded = value[len(_PREFIX) :]
        plaintext = _b64.b64decode(encoded).decode("utf-8")
        logger.debug("encryption_decoded", backend="base64", bytes=len(plaintext))
        return plaintext

    def is_encrypted(self, value: str) -> bool:
        return value.startswith(_PREFIX)
