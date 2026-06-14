"""Unit tests for web/receipts.py — receipt attachment helper."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from starlette.datastructures import Headers, UploadFile

from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.receipt import MAX_RECEIPT_SIZE, Receipt
from web.context import WebActor
from web.receipts import AttachResult, attach_receipts


def _upload(filename: str, data: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def _bill() -> Bill:
    return Bill(id=1, uuid="bill-u", billing_id=1, reference_month="2025-03")


def _billing() -> Billing:
    return Billing(id=1, uuid="billing-u", name="Apt 101")


def _request(bill_service: MagicMock) -> SimpleNamespace:
    actor = WebActor(user_id=1, email="testuser@example.com")
    services = SimpleNamespace(bill=bill_service, audit=MagicMock())
    return SimpleNamespace(
        state=SimpleNamespace(services=services, actor=actor),
        session={},
    )


def _bill_service(receipt: Receipt | None = None) -> MagicMock:
    svc = MagicMock()
    svc.add_receipt.return_value = (
        receipt
        or Receipt(
            id=10,
            uuid="rec-uuid",
            bill_id=1,
            filename="receipt.pdf",
            content_type="application/pdf",
            file_size=9,
        ),
        [],
    )
    return svc


class TestAttachReceipts:
    @pytest.mark.asyncio
    async def test_valid_pdf_attaches_and_audits(self):
        svc = _bill_service()
        request = _request(svc)
        bill, billing = _bill(), _billing()

        result = await attach_receipts(
            request, bill, billing, [_upload("receipt.pdf", b"%PDF-test", "application/pdf")]
        )

        assert result == AttachResult(attached=1, skipped=0, total_bytes=9)
        svc.add_receipt.assert_called_once_with(
            bill=bill,
            billing=billing,
            filename="receipt.pdf",
            file_bytes=b"%PDF-test",
            content_type="application/pdf",
            actor=request.state.actor,
            render=True,
        )
        request.state.services.audit.safe_log_for.assert_called_once_with(
            request.state.actor,
            AuditEventType.RECEIPT_UPLOAD,
            entity_type="receipt",
            entity_id=10,
            entity_uuid="rec-uuid",
            new_state={
                "filename": "receipt.pdf",
                "content_type": "application/pdf",
                "file_size": 9,
                "bill_uuid": "bill-u",
                "billing_uuid": "billing-u",
            },
        )
        assert request.session.get("_messages", []) == []

    @pytest.mark.asyncio
    async def test_invalid_type_skipped_with_warning_flash(self):
        svc = _bill_service()
        request = _request(svc)

        result = await attach_receipts(request, _bill(), _billing(), [_upload("file.gif", b"GIF89a", "image/gif")])

        assert result == AttachResult(attached=0, skipped=1, total_bytes=0)
        svc.add_receipt.assert_not_called()
        messages = request.session["_messages"]
        assert messages == [
            {
                "message": "1 arquivo(s) ignorado(s) (tipo inválido, vazio ou muito grande).",
                "category": "warning",
            }
        ]

    @pytest.mark.asyncio
    async def test_empty_file_skipped(self):
        svc = _bill_service()
        request = _request(svc)

        result = await attach_receipts(request, _bill(), _billing(), [_upload("empty.pdf", b"", "application/pdf")])

        assert result.skipped == 1
        assert result.attached == 0
        svc.add_receipt.assert_not_called()

    @pytest.mark.asyncio
    async def test_oversized_file_skipped(self):
        svc = _bill_service()
        request = _request(svc)
        oversized = b"%PDF-" + b"x" * (MAX_RECEIPT_SIZE + 1)

        result = await attach_receipts(request, _bill(), _billing(), [_upload("big.pdf", oversized, "application/pdf")])

        assert result.skipped == 1
        svc.add_receipt.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_uploadfile_and_blank_filename_ignored_not_skipped(self):
        svc = _bill_service()
        request = _request(svc)
        uploads = ["", _upload("", b"%PDF-test", "application/pdf")]

        result = await attach_receipts(request, _bill(), _billing(), uploads)

        assert result == AttachResult(attached=0, skipped=0, total_bytes=0)
        assert request.session.get("_messages", []) == []

    @pytest.mark.asyncio
    async def test_mixed_valid_and_invalid(self):
        svc = _bill_service()
        request = _request(svc)
        uploads = [
            _upload("ok.pdf", b"%PDF-test", "application/pdf"),
            _upload("bad.gif", b"GIF89a", "image/gif"),
        ]

        result = await attach_receipts(request, _bill(), _billing(), uploads)

        assert result == AttachResult(attached=1, skipped=1, total_bytes=9)
        assert svc.add_receipt.call_count == 1
        assert request.session["_messages"][0]["message"].startswith("1 arquivo(s) ignorado(s)")
