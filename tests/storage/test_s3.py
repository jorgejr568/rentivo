from unittest.mock import MagicMock, patch

import pytest


class TestS3StorageBoto3Missing:
    def test_raises_import_error_when_boto3_is_none(self):
        import rentivo.storage.s3 as s3_module

        with patch.object(s3_module, "boto3", None):
            with pytest.raises(ImportError, match="boto3 is required"):
                s3_module.S3Storage(
                    bucket="b",
                    region="r",
                    access_key_id="k",
                    secret_access_key="s",
                )


class TestS3Storage:
    @patch("rentivo.storage.s3.boto3")
    def test_save_calls_put_object(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        from rentivo.storage.s3 import S3Storage

        storage = S3Storage(
            bucket="my-bucket",
            region="us-east-1",
            access_key_id="key",
            secret_access_key="secret",
        )
        result = storage.save("path/to/file.pdf", b"data")

        mock_client.put_object.assert_called_once_with(
            Bucket="my-bucket",
            Key="path/to/file.pdf",
            Body=b"data",
            ContentType="application/pdf",
        )
        assert result == "path/to/file.pdf"

    @patch("rentivo.storage.s3.boto3")
    def test_get_url_generates_presigned(self, mock_boto3):
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://presigned-url"
        mock_boto3.client.return_value = mock_client

        from rentivo.storage.s3 import S3Storage

        storage = S3Storage(
            bucket="my-bucket",
            region="us-east-1",
            access_key_id="key",
            secret_access_key="secret",
            presigned_expiry=3600,
        )
        url = storage.get_url("path/to/file.pdf")

        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "my-bucket", "Key": "path/to/file.pdf"},
            ExpiresIn=3600,
        )
        assert url == "https://presigned-url"

    @patch("rentivo.storage.s3.boto3")
    def test_endpoint_url_passed(self, mock_boto3):
        mock_boto3.client.return_value = MagicMock()

        from rentivo.storage.s3 import S3Storage

        S3Storage(
            bucket="b",
            region="r",
            access_key_id="k",
            secret_access_key="s",
            endpoint_url="https://custom.endpoint",
        )
        call_kwargs = mock_boto3.client.call_args[1]
        assert call_kwargs["endpoint_url"] == "https://custom.endpoint"

    @patch("rentivo.storage.s3.boto3")
    def test_no_endpoint_url(self, mock_boto3):
        mock_boto3.client.return_value = MagicMock()

        from rentivo.storage.s3 import S3Storage

        S3Storage(bucket="b", region="r", access_key_id="k", secret_access_key="s")
        call_kwargs = mock_boto3.client.call_args[1]
        assert "endpoint_url" not in call_kwargs

    @patch("rentivo.storage.s3.boto3")
    def test_get_calls_get_object(self, mock_boto3):
        mock_client = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"file-contents"
        mock_client.get_object.return_value = {"Body": mock_body}
        mock_boto3.client.return_value = mock_client

        from rentivo.storage.s3 import S3Storage

        storage = S3Storage(
            bucket="my-bucket",
            region="us-east-1",
            access_key_id="key",
            secret_access_key="secret",
        )
        data = storage.get("path/to/file.pdf")

        mock_client.get_object.assert_called_once_with(Bucket="my-bucket", Key="path/to/file.pdf")
        assert data == b"file-contents"

    @patch("rentivo.storage.s3.boto3")
    def test_save_with_content_type(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        from rentivo.storage.s3 import S3Storage

        storage = S3Storage(
            bucket="my-bucket",
            region="us-east-1",
            access_key_id="key",
            secret_access_key="secret",
        )
        result = storage.save("path/to/img.jpg", b"jpeg-data", content_type="image/jpeg")

        mock_client.put_object.assert_called_once_with(
            Bucket="my-bucket",
            Key="path/to/img.jpg",
            Body=b"jpeg-data",
            ContentType="image/jpeg",
        )
        assert result == "path/to/img.jpg"
