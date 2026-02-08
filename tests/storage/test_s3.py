from unittest.mock import MagicMock, patch


class TestS3Storage:
    @patch("landlord.storage.s3.boto3")
    def test_save_calls_put_object(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        from landlord.storage.s3 import S3Storage

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

    @patch("landlord.storage.s3.boto3")
    def test_get_url_generates_presigned(self, mock_boto3):
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://presigned-url"
        mock_boto3.client.return_value = mock_client

        from landlord.storage.s3 import S3Storage

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

    @patch("landlord.storage.s3.boto3")
    def test_endpoint_url_passed(self, mock_boto3):
        mock_boto3.client.return_value = MagicMock()

        from landlord.storage.s3 import S3Storage

        S3Storage(
            bucket="b",
            region="r",
            access_key_id="k",
            secret_access_key="s",
            endpoint_url="https://custom.endpoint",
        )
        call_kwargs = mock_boto3.client.call_args[1]
        assert call_kwargs["endpoint_url"] == "https://custom.endpoint"

    @patch("landlord.storage.s3.boto3")
    def test_no_endpoint_url(self, mock_boto3):
        mock_boto3.client.return_value = MagicMock()

        from landlord.storage.s3 import S3Storage

        S3Storage(
            bucket="b", region="r", access_key_id="k", secret_access_key="s"
        )
        call_kwargs = mock_boto3.client.call_args[1]
        assert "endpoint_url" not in call_kwargs
