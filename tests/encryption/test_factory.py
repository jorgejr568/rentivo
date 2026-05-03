from __future__ import annotations

from unittest.mock import patch

import pytest

from rentivo.encryption.base64 import Base64Backend


class TestEncryptionFactory:
    @patch("rentivo.encryption.factory.settings")
    def test_returns_base64_backend_by_default(self, mock_settings):
        mock_settings.encryption_backend = "base64"

        from rentivo.encryption.factory import get_encryption

        backend = get_encryption()
        assert isinstance(backend, Base64Backend)

    @patch("rentivo.encryption.factory.settings")
    def test_returns_kms_backend_when_configured(self, mock_settings):
        mock_settings.encryption_backend = "kms"
        mock_settings.kms_key_id = "alias/rentivo"
        mock_settings.kms_region = "us-east-1"
        mock_settings.kms_access_key_id = "key"
        mock_settings.kms_secret_access_key = "secret"
        mock_settings.kms_endpoint_url = ""

        with patch("rentivo.encryption.kms.boto3"):
            from rentivo.encryption.factory import get_encryption
            from rentivo.encryption.kms import KMSBackend

            backend = get_encryption()
            assert isinstance(backend, KMSBackend)

    @patch("rentivo.encryption.factory.settings")
    def test_unsupported_backend(self, mock_settings):
        mock_settings.encryption_backend = "rot13"

        from rentivo.encryption.factory import get_encryption

        with pytest.raises(ValueError, match="Unsupported encryption backend"):
            get_encryption()
