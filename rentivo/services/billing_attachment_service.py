from __future__ import annotations

import structlog
from ulid import ULID

from rentivo.models.billing import Billing
from rentivo.models.billing_attachment import (
    ALLOWED_ATTACHMENT_TYPES,
    MAX_ATTACHMENT_SIZE,
    BillingAttachment,
)
from rentivo.observability import traced
from rentivo.repositories.base import BillingAttachmentRepository
from rentivo.settings import settings
from rentivo.storage.base import FileRef, StorageBackend

logger = structlog.get_logger(__name__)

_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


def _attachment_storage_key(billing_uuid: str, attachment_uuid: str, content_type: str) -> str:
    ext = _EXTENSIONS.get(content_type, "")
    key = f"{billing_uuid}/attachments/{attachment_uuid}{ext}"
    prefix = settings.storage_prefix
    return f"{prefix}/{key}" if prefix else key


class BillingAttachmentService:
    """Manage named documents attached to a billing (contracts, etc.).

    Attachments are standalone files — they are stored and served directly,
    never merged into a bill PDF.
    """

    def __init__(self, repo: BillingAttachmentRepository, storage: StorageBackend) -> None:
        self.repo = repo
        self.storage = storage

    @traced("billing_attachment.add_attachment")
    def add_attachment(
        self,
        billing: Billing,
        name: str,
        filename: str,
        file_bytes: bytes,
        content_type: str,
    ) -> BillingAttachment:
        if billing.id is None:
            raise ValueError("Cannot add attachment to billing without an id")
        if content_type not in ALLOWED_ATTACHMENT_TYPES:
            raise ValueError(f"Unsupported file type: {content_type}")
        if len(file_bytes) > MAX_ATTACHMENT_SIZE:
            raise ValueError("File too large")
        if not file_bytes:
            raise ValueError("Empty file")

        label = name.strip() or filename
        attachment_uuid = str(ULID())
        storage_key = _attachment_storage_key(billing.uuid, attachment_uuid, content_type)

        existing = self.repo.list_by_billing(billing.id)
        sort_order = max((a.sort_order for a in existing), default=-1) + 1

        self.storage.save(storage_key, file_bytes, content_type=content_type)
        try:
            attachment = self.repo.create(
                BillingAttachment(
                    billing_id=billing.id,
                    name=label,
                    filename=filename,
                    storage_key=storage_key,
                    content_type=content_type,
                    file_size=len(file_bytes),
                    sort_order=sort_order,
                )
            )
        except Exception:
            logger.exception("attachment_create_failed_cleanup", storage_key=storage_key)
            self.storage.delete(storage_key)
            raise
        logger.info(
            "attachment_added",
            attachment_uuid=attachment.uuid,
            billing_uuid=billing.uuid,
            name=label,
        )
        return attachment

    @traced("billing_attachment.list_attachments")
    def list_attachments(self, billing_id: int) -> list[BillingAttachment]:
        return self.repo.list_by_billing(billing_id)

    @traced("billing_attachment.get_attachment_by_uuid")
    def get_attachment_by_uuid(self, uuid: str) -> BillingAttachment | None:
        return self.repo.get_by_uuid(uuid)

    @traced("billing_attachment.delete_attachment")
    def delete_attachment(self, attachment: BillingAttachment) -> None:
        if attachment.id is None:
            raise ValueError("Cannot delete attachment without an id")
        self.repo.delete(attachment.id)
        logger.info("attachment_deleted", attachment_uuid=attachment.uuid)

    @traced("billing_attachment.get_attachment_ref")
    def get_attachment_ref(self, attachment: BillingAttachment) -> FileRef:
        return self.storage.get_ref(attachment.storage_key)
