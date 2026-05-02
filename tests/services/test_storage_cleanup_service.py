from unittest.mock import MagicMock

from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.receipt import Receipt
from rentivo.services.storage_cleanup_service import StorageCleanupService


def _make_service(*, bills=None, receipts_by_bill=None):
    job_service = MagicMock()
    bill_repo = MagicMock()
    receipt_repo = MagicMock()
    bill_repo.list_by_billing.return_value = bills or []
    receipt_repo.list_by_bill.side_effect = lambda bill_id: (receipts_by_bill or {}).get(bill_id, [])
    return (
        StorageCleanupService(job_service, bill_repo, receipt_repo),
        job_service,
        bill_repo,
        receipt_repo,
    )


def test_enqueue_key_skips_empty_string():
    svc, job, _, _ = _make_service()

    svc.enqueue_key("")

    job.enqueue.assert_not_called()


def test_enqueue_key_skips_none():
    svc, job, _, _ = _make_service()

    svc.enqueue_key(None)  # type: ignore[arg-type]

    job.enqueue.assert_not_called()


def test_enqueue_key_calls_job_service_with_correct_shape():
    svc, job, _, _ = _make_service()

    svc.enqueue_key("billing/bill.pdf", source="web", actor_id=7, actor_username="a@x")

    job.enqueue.assert_called_once_with(
        "s3.delete",
        {"key": "billing/bill.pdf"},
        source="web",
        actor_id=7,
        actor_username="a@x",
    )


def test_enqueue_key_default_actor_args():
    svc, job, _, _ = _make_service()

    svc.enqueue_key("k")

    job.enqueue.assert_called_once_with(
        "s3.delete",
        {"key": "k"},
        source="web",
        actor_id=None,
        actor_username="",
    )


def test_enqueue_receipt_delete_uses_storage_key():
    svc, job, _, _ = _make_service()
    receipt = Receipt(id=1, bill_id=1, filename="r.pdf", storage_key="b/r.pdf")

    svc.enqueue_receipt_delete(receipt, source="web", actor_id=7, actor_username="a@x")

    job.enqueue.assert_called_once_with(
        "s3.delete",
        {"key": "b/r.pdf"},
        source="web",
        actor_id=7,
        actor_username="a@x",
    )


def test_enqueue_receipt_delete_skips_empty_storage_key():
    svc, job, _, _ = _make_service()
    receipt = Receipt(id=1, bill_id=1, filename="r.pdf", storage_key="")

    svc.enqueue_receipt_delete(receipt)

    job.enqueue.assert_not_called()


def test_enqueue_bill_delete_cascade_emits_receipts_then_pdf():
    bill = Bill(id=10, uuid="bill-u", billing_id=1, reference_month="2025-03", pdf_path="b/bill.pdf")
    receipts = [
        Receipt(id=1, bill_id=10, filename="r1.pdf", storage_key="b/bill/r1.pdf"),
        Receipt(id=2, bill_id=10, filename="r2.pdf", storage_key="b/bill/r2.pdf"),
    ]
    svc, job, _, receipt_repo = _make_service(receipts_by_bill={10: receipts})

    svc.enqueue_bill_delete_cascade(bill, source="web", actor_id=7, actor_username="a@x")

    receipt_repo.list_by_bill.assert_called_once_with(10)
    keys = [call.args[1]["key"] for call in job.enqueue.call_args_list]
    assert keys == ["b/bill/r1.pdf", "b/bill/r2.pdf", "b/bill.pdf"]
    for call in job.enqueue.call_args_list:
        assert call.args[0] == "s3.delete"
        assert call.kwargs == {"source": "web", "actor_id": 7, "actor_username": "a@x"}


def test_enqueue_bill_delete_cascade_skips_empty_pdf_path():
    bill = Bill(id=10, uuid="u", billing_id=1, reference_month="2025-03", pdf_path="")
    svc, job, _, _ = _make_service(
        receipts_by_bill={
            10: [
                Receipt(id=1, bill_id=10, filename="r.pdf", storage_key="b/bill/r.pdf"),
            ]
        }
    )

    svc.enqueue_bill_delete_cascade(bill)

    keys = [call.args[1]["key"] for call in job.enqueue.call_args_list]
    assert keys == ["b/bill/r.pdf"]


def test_enqueue_bill_delete_cascade_handles_bill_id_none():
    bill = Bill(id=None, uuid="u", billing_id=1, reference_month="2025-03", pdf_path="b/bill.pdf")
    svc, job, _, receipt_repo = _make_service()

    svc.enqueue_bill_delete_cascade(bill)

    receipt_repo.list_by_bill.assert_not_called()
    keys = [call.args[1]["key"] for call in job.enqueue.call_args_list]
    assert keys == ["b/bill.pdf"]


def test_enqueue_billing_delete_cascade_walks_bills_and_receipts():
    billing = Billing(id=99, uuid="bill-99", name="Apt")
    bills = [
        Bill(id=1, uuid="b1", billing_id=99, reference_month="2025-01", pdf_path="b/b1.pdf"),
        Bill(id=2, uuid="b2", billing_id=99, reference_month="2025-02", pdf_path="b/b2.pdf"),
    ]
    receipts_by_bill = {
        1: [Receipt(id=11, bill_id=1, filename="x", storage_key="b/b1/r1.pdf")],
        2: [
            Receipt(id=21, bill_id=2, filename="x", storage_key="b/b2/r1.pdf"),
            Receipt(id=22, bill_id=2, filename="x", storage_key="b/b2/r2.pdf"),
        ],
    }
    svc, job, bill_repo, receipt_repo = _make_service(bills=bills, receipts_by_bill=receipts_by_bill)

    svc.enqueue_billing_delete_cascade(billing, source="web", actor_id=7, actor_username="a@x")

    bill_repo.list_by_billing.assert_called_once_with(99)
    keys = [call.args[1]["key"] for call in job.enqueue.call_args_list]
    assert keys == [
        "b/b1/r1.pdf",
        "b/b1.pdf",
        "b/b2/r1.pdf",
        "b/b2/r2.pdf",
        "b/b2.pdf",
    ]


def test_enqueue_billing_delete_cascade_billing_id_none_is_noop():
    billing = Billing(id=None, uuid="u", name="Apt")
    svc, job, bill_repo, _ = _make_service()

    svc.enqueue_billing_delete_cascade(billing)

    bill_repo.list_by_billing.assert_not_called()
    job.enqueue.assert_not_called()


def test_enqueue_billing_delete_cascade_with_no_bills_is_noop():
    billing = Billing(id=99, uuid="u", name="Apt")
    svc, job, bill_repo, _ = _make_service(bills=[])

    svc.enqueue_billing_delete_cascade(billing)

    bill_repo.list_by_billing.assert_called_once_with(99)
    job.enqueue.assert_not_called()
