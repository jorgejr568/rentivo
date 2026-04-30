import structlog

from rentivo.email.base import EmailBackend
from rentivo.settings import settings

logger = structlog.get_logger(__name__)


def get_email_backend() -> EmailBackend:
    backend = settings.email_backend
    if backend == "local":
        from rentivo.email.local import LocalEmailBackend
        logger.info("email_backend_selected", backend="local", path=settings.email_local_path)
        return LocalEmailBackend(settings.email_local_path)

    if backend == "ses":
        from rentivo.email.ses import SESEmailBackend
        logger.info("email_backend_selected", backend="ses", region=settings.ses_region)
        return SESEmailBackend(
            region=settings.ses_region,
            access_key_id=settings.ses_access_key_id,
            secret_access_key=settings.ses_secret_access_key,
            from_address=settings.ses_from_email,
            endpoint_url=settings.ses_endpoint_url,
            configuration_set=settings.ses_configuration_set,
        )

    raise ValueError(f"Unsupported email backend: {backend}")
