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


def test_decrypt_many_default_falls_back_to_sequential_decrypt():
    """Backends that don't override decrypt_many should still work via the
    sequential default in the base class — same plaintexts, same order."""

    class Echo(EncryptionBackend):
        def encrypt(self, plaintext: str) -> str:
            return plaintext

        def decrypt(self, value: str) -> str:
            return value.upper()

        def is_encrypted(self, value: str) -> bool:
            return False

    backend = Echo()
    assert backend.decrypt_many(["a", "b", "c"]) == ["A", "B", "C"]
    assert backend.decrypt_many([]) == []
