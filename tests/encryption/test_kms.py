from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

CIPHERTEXT_PREFIX = "enc:v1:"


class TestKMSBackendBoto3Missing:
    def test_raises_import_error_when_boto3_is_none(self):
        import rentivo.encryption.kms as kms_module

        with patch.object(kms_module, "boto3", None):
            with pytest.raises(ImportError, match="boto3 is required"):
                kms_module.KMSBackend(
                    key_id="alias/rentivo",
                    region="us-east-1",
                    access_key_id="k",
                    secret_access_key="s",
                )


class TestKMSBackend:
    @patch("rentivo.encryption.kms.boto3")
    def test_encrypt_calls_kms_and_returns_prefixed_base64(self, mock_boto3):
        mock_client = MagicMock()
        mock_client.encrypt.return_value = {"CiphertextBlob": b"ciphertext-blob-bytes"}
        mock_boto3.client.return_value = mock_client

        from rentivo.encryption.kms import KMSBackend

        backend = KMSBackend(
            key_id="alias/rentivo",
            region="us-east-1",
            access_key_id="k",
            secret_access_key="s",
        )
        result = backend.encrypt("test@pix.com")

        mock_client.encrypt.assert_called_once_with(
            KeyId="alias/rentivo",
            Plaintext=b"test@pix.com",
        )
        assert result.startswith(CIPHERTEXT_PREFIX)
        body = result[len(CIPHERTEXT_PREFIX) :]
        assert base64.b64decode(body) == b"ciphertext-blob-bytes"

    @patch("rentivo.encryption.kms.boto3")
    def test_decrypt_calls_kms_with_decoded_blob(self, mock_boto3):
        mock_client = MagicMock()
        mock_client.decrypt.return_value = {"Plaintext": b"test@pix.com"}
        mock_boto3.client.return_value = mock_client

        from rentivo.encryption.kms import KMSBackend

        backend = KMSBackend(
            key_id="alias/rentivo",
            region="us-east-1",
            access_key_id="k",
            secret_access_key="s",
        )
        ciphertext = CIPHERTEXT_PREFIX + base64.b64encode(b"ciphertext-blob-bytes").decode()
        result = backend.decrypt(ciphertext)

        mock_client.decrypt.assert_called_once_with(
            CiphertextBlob=b"ciphertext-blob-bytes",
            KeyId="alias/rentivo",
        )
        assert result == "test@pix.com"

    @patch("rentivo.encryption.kms.boto3")
    def test_round_trip_via_mock(self, mock_boto3):
        """Simulate a full round-trip with a stub that maps blobs to plaintexts."""
        mock_client = MagicMock()
        store: dict[bytes, bytes] = {}

        def fake_encrypt(KeyId, Plaintext):
            blob = b"BLOB-" + Plaintext
            store[blob] = Plaintext
            return {"CiphertextBlob": blob}

        def fake_decrypt(CiphertextBlob, KeyId):
            return {"Plaintext": store[CiphertextBlob]}

        mock_client.encrypt.side_effect = fake_encrypt
        mock_client.decrypt.side_effect = fake_decrypt
        mock_boto3.client.return_value = mock_client

        from rentivo.encryption.kms import KMSBackend

        backend = KMSBackend(
            key_id="alias/rentivo",
            region="us-east-1",
            access_key_id="k",
            secret_access_key="s",
        )

        for value in ("test@pix.com", "12345678901", "+5511987654321", "Some Merchant"):
            assert backend.decrypt(backend.encrypt(value)) == value

    @patch("rentivo.encryption.kms.boto3")
    def test_encrypt_is_idempotent_on_already_encrypted(self, mock_boto3):
        """encrypt() on an already-encrypted value must not call KMS again."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        from rentivo.encryption.kms import KMSBackend

        backend = KMSBackend(
            key_id="alias/rentivo",
            region="us-east-1",
            access_key_id="k",
            secret_access_key="s",
        )
        ciphertext = CIPHERTEXT_PREFIX + base64.b64encode(b"already-encrypted").decode()
        result = backend.encrypt(ciphertext)

        assert result == ciphertext
        mock_client.encrypt.assert_not_called()

    @patch("rentivo.encryption.kms.boto3")
    def test_decrypt_passes_through_plaintext(self, mock_boto3):
        """decrypt() on a plaintext value must not call KMS."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        from rentivo.encryption.kms import KMSBackend

        backend = KMSBackend(
            key_id="alias/rentivo",
            region="us-east-1",
            access_key_id="k",
            secret_access_key="s",
        )
        result = backend.decrypt("test@pix.com")

        assert result == "test@pix.com"
        mock_client.decrypt.assert_not_called()

    @patch("rentivo.encryption.kms.boto3")
    def test_decrypt_handles_transitional_base64_rows(self, mock_boto3):
        """During the backfill window, KMS reads must transparently decode
        rows that were written under Base64Backend before the cutover."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        from rentivo.encryption.kms import KMSBackend

        backend = KMSBackend(
            key_id="alias/rentivo",
            region="us-east-1",
            access_key_id="k",
            secret_access_key="s",
        )
        # b64:v1:dGVzdEBwaXguY29t == base64("test@pix.com")
        b64_row = "b64:v1:" + base64.b64encode(b"test@pix.com").decode()
        result = backend.decrypt(b64_row)

        assert result == "test@pix.com"
        mock_client.decrypt.assert_not_called()

    @patch("rentivo.encryption.kms.boto3")
    def test_encrypt_empty_string_is_no_op(self, mock_boto3):
        """Empty string never goes to KMS — it is its own ciphertext."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        from rentivo.encryption.kms import KMSBackend

        backend = KMSBackend(
            key_id="alias/rentivo",
            region="us-east-1",
            access_key_id="k",
            secret_access_key="s",
        )
        assert backend.encrypt("") == ""
        mock_client.encrypt.assert_not_called()

    @patch("rentivo.encryption.kms.boto3")
    def test_decrypt_empty_string_is_no_op(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        from rentivo.encryption.kms import KMSBackend

        backend = KMSBackend(
            key_id="alias/rentivo",
            region="us-east-1",
            access_key_id="k",
            secret_access_key="s",
        )
        assert backend.decrypt("") == ""
        mock_client.decrypt.assert_not_called()

    @patch("rentivo.encryption.kms.boto3")
    def test_is_encrypted_recognizes_prefix(self, mock_boto3):
        mock_boto3.client.return_value = MagicMock()

        from rentivo.encryption.kms import KMSBackend

        backend = KMSBackend(
            key_id="alias/rentivo",
            region="us-east-1",
            access_key_id="k",
            secret_access_key="s",
        )
        assert backend.is_encrypted(CIPHERTEXT_PREFIX + "anything") is True
        assert backend.is_encrypted("plaintext") is False
        assert backend.is_encrypted("") is False
        assert backend.is_encrypted("enc:v2:future") is False  # different version

    @patch("rentivo.encryption.kms.boto3")
    def test_endpoint_url_passed(self, mock_boto3):
        mock_boto3.client.return_value = MagicMock()

        from rentivo.encryption.kms import KMSBackend

        KMSBackend(
            key_id="alias/rentivo",
            region="us-east-1",
            access_key_id="k",
            secret_access_key="s",
            endpoint_url="https://localhost.localstack.cloud:4566",
        )
        call_kwargs = mock_boto3.client.call_args[1]
        assert call_kwargs["endpoint_url"] == "https://localhost.localstack.cloud:4566"

    @patch("rentivo.encryption.kms.boto3")
    def test_no_endpoint_url(self, mock_boto3):
        mock_boto3.client.return_value = MagicMock()

        from rentivo.encryption.kms import KMSBackend

        KMSBackend(
            key_id="alias/rentivo",
            region="us-east-1",
            access_key_id="k",
            secret_access_key="s",
        )
        call_kwargs = mock_boto3.client.call_args[1]
        assert "endpoint_url" not in call_kwargs
