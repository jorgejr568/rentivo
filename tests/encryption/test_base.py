from __future__ import annotations

import pytest

from rentivo.encryption.base import EncryptionBackend


def test_encryption_backend_is_abstract():
    with pytest.raises(TypeError):
        EncryptionBackend()  # type: ignore[abstract]


def test_encryption_backend_requires_encrypt_decrypt_is_encrypted():
    class Incomplete(EncryptionBackend):
        def encrypt(self, plaintext: str) -> str:
            return plaintext

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]
