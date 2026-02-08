from unittest.mock import patch

import pytest

from landlord.storage.local import LocalStorage


class TestStorageFactory:
    @patch("landlord.storage.factory.settings")
    def test_local_storage(self, mock_settings, tmp_path):
        mock_settings.storage_backend = "local"
        mock_settings.storage_local_path = str(tmp_path)

        from landlord.storage.factory import get_storage

        storage = get_storage()
        assert isinstance(storage, LocalStorage)

    @patch("landlord.storage.factory.settings")
    def test_s3_storage(self, mock_settings):
        mock_settings.storage_backend = "s3"
        mock_settings.s3_bucket = "bucket"
        mock_settings.s3_region = "us-east-1"
        mock_settings.s3_access_key_id = "key"
        mock_settings.s3_secret_access_key = "secret"
        mock_settings.s3_endpoint_url = ""
        mock_settings.s3_presigned_expiry = 3600

        with patch("landlord.storage.s3.boto3"):
            from landlord.storage.factory import get_storage
            from landlord.storage.s3 import S3Storage

            storage = get_storage()
            assert isinstance(storage, S3Storage)

    @patch("landlord.storage.factory.settings")
    def test_unsupported_backend(self, mock_settings):
        mock_settings.storage_backend = "ftp"

        from landlord.storage.factory import get_storage

        with pytest.raises(ValueError, match="Unsupported storage backend"):
            get_storage()
