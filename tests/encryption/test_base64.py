from __future__ import annotations

import base64

from rentivo.encryption.base64 import Base64Backend

PREFIX = "b64:v1:"


class TestBase64Backend:
    def test_encrypt_returns_prefixed_base64(self):
        backend = Base64Backend()
        result = backend.encrypt("test@pix.com")
        assert result.startswith(PREFIX)
        body = result[len(PREFIX) :]
        assert base64.b64decode(body).decode() == "test@pix.com"

    def test_encrypt_empty_string_is_empty(self):
        """Empty string is its own ciphertext — no prefix added."""
        backend = Base64Backend()
        assert backend.encrypt("") == ""

    def test_decrypt_round_trip(self):
        backend = Base64Backend()
        for value in ("foo", "bar@example.com", "12345678901", "+5511987654321", "São Paulo"):
            assert backend.decrypt(backend.encrypt(value)) == value

    def test_decrypt_empty_string_is_empty(self):
        backend = Base64Backend()
        assert backend.decrypt("") == ""

    def test_decrypt_passes_through_plaintext(self):
        """Legacy plaintext rows must read back unchanged."""
        backend = Base64Backend()
        assert backend.decrypt("alice@pix.com") == "alice@pix.com"
        assert backend.decrypt("12345678901") == "12345678901"

    def test_encrypt_is_idempotent_on_already_encoded(self):
        backend = Base64Backend()
        ciphertext = backend.encrypt("test@pix.com")
        assert backend.encrypt(ciphertext) == ciphertext

    def test_is_encrypted_recognizes_own_prefix_only(self):
        backend = Base64Backend()
        assert backend.is_encrypted(PREFIX + "anything") is True
        assert backend.is_encrypted("plaintext") is False
        assert backend.is_encrypted("") is False
        # Foreign prefix from KMSBackend must not be claimed by Base64Backend.
        assert backend.is_encrypted("enc:v1:notmine") is False


class TestBase64BackendDecryptMany:
    def test_decrypt_many_round_trips_in_order(self):
        from rentivo.encryption.base64 import Base64Backend

        backend = Base64Backend()
        plaintexts = ["a", "b@example.com", "Açaí — São Paulo"]
        ciphertexts = [backend.encrypt(p) for p in plaintexts]
        assert backend.decrypt_many(ciphertexts) == plaintexts

    def test_decrypt_many_handles_mixed_inputs(self):
        from rentivo.encryption.base64 import Base64Backend

        backend = Base64Backend()
        encrypted = backend.encrypt("encrypted")
        result = backend.decrypt_many(["", "raw", encrypted])
        assert result == ["", "raw", "encrypted"]
