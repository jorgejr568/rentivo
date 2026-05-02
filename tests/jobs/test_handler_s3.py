from unittest.mock import MagicMock, patch

import pytest

from rentivo.jobs.base import PermanentJobError


def _make_client_error(code: str):
    """Return a botocore.exceptions.ClientError with the given Code."""
    from botocore.exceptions import ClientError

    return ClientError({"Error": {"Code": code, "Message": "test"}}, "DeleteObject")


def test_handler_calls_storage_delete_with_key():
    storage = MagicMock()
    with patch("rentivo.jobs.handlers.s3.get_storage", return_value=storage):
        from rentivo.jobs.handlers.s3 import handle_s3_delete

        handle_s3_delete({"key": "billing/bill.pdf"})

    storage.delete.assert_called_once_with("billing/bill.pdf")


def test_handler_empty_key_is_no_op():
    storage = MagicMock()
    with patch("rentivo.jobs.handlers.s3.get_storage", return_value=storage):
        from rentivo.jobs.handlers.s3 import handle_s3_delete

        handle_s3_delete({"key": ""})

    storage.delete.assert_not_called()


def test_handler_missing_key_is_no_op():
    storage = MagicMock()
    with patch("rentivo.jobs.handlers.s3.get_storage", return_value=storage):
        from rentivo.jobs.handlers.s3 import handle_s3_delete

        handle_s3_delete({})

    storage.delete.assert_not_called()


def test_handler_swallows_no_such_key():
    """Idempotent: deleting an already-deleted key is the desired end state."""
    storage = MagicMock()
    storage.delete.side_effect = _make_client_error("NoSuchKey")
    with patch("rentivo.jobs.handlers.s3.get_storage", return_value=storage):
        from rentivo.jobs.handlers.s3 import handle_s3_delete

        handle_s3_delete({"key": "k"})  # must not raise


def test_handler_swallows_404():
    storage = MagicMock()
    storage.delete.side_effect = _make_client_error("404")
    with patch("rentivo.jobs.handlers.s3.get_storage", return_value=storage):
        from rentivo.jobs.handlers.s3 import handle_s3_delete

        handle_s3_delete({"key": "k"})


@pytest.mark.parametrize(
    "code",
    [
        "NoSuchBucket",
        "InvalidBucketName",
        "AccessDenied",
        "AllAccessDisabled",
        "InvalidAccessKeyId",
        "SignatureDoesNotMatch",
    ],
)
def test_handler_raises_permanent_for_config_errors(code: str):
    storage = MagicMock()
    storage.delete.side_effect = _make_client_error(code)
    with patch("rentivo.jobs.handlers.s3.get_storage", return_value=storage):
        from rentivo.jobs.handlers.s3 import handle_s3_delete

        with pytest.raises(PermanentJobError, match="s3 config error"):
            handle_s3_delete({"key": "k"})


@pytest.mark.parametrize("code", ["SlowDown", "RequestTimeout", "ServiceUnavailable", "InternalError"])
def test_handler_reraises_retryable_aws_codes(code: str):
    from botocore.exceptions import ClientError

    storage = MagicMock()
    storage.delete.side_effect = _make_client_error(code)
    with patch("rentivo.jobs.handlers.s3.get_storage", return_value=storage):
        from rentivo.jobs.handlers.s3 import handle_s3_delete

        with pytest.raises(ClientError):
            handle_s3_delete({"key": "k"})


def test_handler_reraises_generic_runtime_error():
    storage = MagicMock()
    storage.delete.side_effect = RuntimeError("network blip")
    with patch("rentivo.jobs.handlers.s3.get_storage", return_value=storage):
        from rentivo.jobs.handlers.s3 import handle_s3_delete

        with pytest.raises(RuntimeError, match="network blip"):
            handle_s3_delete({"key": "k"})


def test_classifier_returns_success_for_idempotent_codes():
    from rentivo.jobs.handlers.s3 import _classify_boto_client_error

    assert _classify_boto_client_error(_make_client_error("NoSuchKey")) == "success"
    assert _classify_boto_client_error(_make_client_error("404")) == "success"


def test_classifier_returns_permanent_for_config_codes():
    from rentivo.jobs.handlers.s3 import _classify_boto_client_error

    assert _classify_boto_client_error(_make_client_error("NoSuchBucket")) == "permanent"
    assert _classify_boto_client_error(_make_client_error("AccessDenied")) == "permanent"


def test_classifier_returns_retry_for_unknown_codes():
    from rentivo.jobs.handlers.s3 import _classify_boto_client_error

    assert _classify_boto_client_error(_make_client_error("SlowDown")) == "retry"
    assert _classify_boto_client_error(_make_client_error("ZZZUnknown")) == "retry"


def test_classifier_handles_missing_response_attribute():
    from rentivo.jobs.handlers.s3 import _classify_boto_client_error

    class FakeError(Exception):
        pass

    # No `.response` attribute → empty code → "retry"
    assert _classify_boto_client_error(FakeError("oops")) == "retry"


def test_classifier_handles_response_without_error_dict():
    from rentivo.jobs.handlers.s3 import _classify_boto_client_error

    class FakeError(Exception):
        response = {"NotError": {"Code": "X"}}  # malformed

    assert _classify_boto_client_error(FakeError()) == "retry"
