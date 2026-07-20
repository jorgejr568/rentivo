from __future__ import annotations

import structlog

from rentivo.jobs.base import PermanentJobError
from rentivo.jobs.registry import register
from rentivo.storage.factory import get_storage

logger = structlog.get_logger(__name__)

# Boto3 ClientError codes that mean "the bucket / config is broken; retrying
# would just rerun the same broken request 5 times".
_PERMANENT_S3_CODES = frozenset(
    {
        "NoSuchBucket",
        "InvalidBucketName",
        "AccessDenied",
        "AllAccessDisabled",
        "InvalidAccessKeyId",
        "SignatureDoesNotMatch",
    }
)

# Codes that mean "the key was already gone" — desired end-state already met.
_IDEMPOTENT_S3_CODES = frozenset({"NoSuchKey", "404"})


def _classify_boto_client_error(exc: Exception) -> str:
    """Return 'success' | 'permanent' | 'retry' for a boto3 ClientError.

    Any exception whose `response` does not look like the documented boto3
    shape is treated as 'retry' — better to retry an unrecognized error than
    to silently dead-letter or silently swallow it.
    """
    code = ""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error")
        if isinstance(error, dict):
            code = error.get("Code", "") or ""
    if code in _IDEMPOTENT_S3_CODES:
        return "success"
    if code in _PERMANENT_S3_CODES:
        return "permanent"
    return "retry"


@register("s3.delete")
def handle_s3_delete(payload: dict) -> None:
    key = payload.get("key", "")
    if not key:
        logger.warning("s3_delete_empty_key", payload=payload)
        return

    storage = get_storage()
    try:
        storage.delete(key)
    except Exception as exc:
        try:
            from botocore.exceptions import ClientError
        except ImportError:  # pragma: no cover — boto3 absent in local-only deploys
            ClientError = ()  # type: ignore[assignment]
        if isinstance(exc, ClientError):
            verdict = _classify_boto_client_error(exc)
            if verdict == "success":
                logger.info("s3_delete_already_gone", key=key)
                return
            if verdict == "permanent":
                raise PermanentJobError(f"s3 config error: {exc}") from exc
        raise
    logger.info("s3_delete_succeeded", key=key)
