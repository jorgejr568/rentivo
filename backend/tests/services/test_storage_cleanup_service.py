from unittest.mock import MagicMock

from rentivo.context import Actor
from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.receipt import Receipt
from rentivo.services.storage_cleanup_service import StorageCleanupService


def _actor():
    return Actor(source="web", user_id=7, email="a@x")


def _make_service(*, bills=None, receipts_by_bill=None, attachments=None):
    job_service = MagicMock()
    bill_repo = MagicMock()
    receipt_repo = MagicMock()
    attachment_repo = MagicMock()
    bill_repo.list_by_billing.return_value = bills or []
    receipt_repo.list_by_bill.side_effect = lambda bill_id: (receipts_by_bill or {}).get(bill_id, [])
    attachment_repo.list_by_billing.return_value = attachments or []
    return (
        StorageCleanupService(job_service, bill_repo, receipt_repo, attachment_repo),
        job_service,
        bill_repo,
        receipt_repo,
    )


def test_enqueue_key_skips_empty_string():
    svc, job, _, _ = _make_service()

    svc.enqueue_key(_actor(), "")

    job.enqueue_for.assert_not_called()


def test_enqueue_key_skips_none():
    svc, job, _, _ = _make_service()

    svc.enqueue_key(_actor(), None)

    job.enqueue_for.assert_not_called()


def test_enqueue_key_passes_actor_to_enqueue_for():
    svc, job, _, _ = _make_service()
    actor = _actor()

    svc.enqueue_key(actor, "billing/bill.pdf")

    job.enqueue_for.assert_called_once_with(actor, "s3.delete", {"key": "billing/bill.pdf"})


def test_enqueue_receipt_delete_uses_storage_key():
    svc, job, _, _ = _make_service()
    actor = _actor()
    receipt = Receipt(id=1, bill_id=1, filename="r.pdf", storage_key="b/r.pdf")

    svc.enqueue_receipt_delete(actor, receipt)

    job.enqueue_for.assert_called_once_with(actor, "s3.delete", {"key": "b/r.pdf"})


def test_enqueue_receipt_delete_skips_empty_storage_key():
    svc, job, _, _ = _make_service()
    receipt = Receipt(id=1, bill_id=1, filename="r.pdf", storage_key="")

    svc.enqueue_receipt_delete(_actor(), receipt)

    job.enqueue_for.assert_not_called()


def test_enqueue_bill_delete_cascade_emits_receipts_then_pdf():
    bill = Bill(id=10, uuid="bill-u", billing_id=1, reference_month="2025-03", pdf_path="b/bill.pdf")
    receipts = [
        Receipt(id=1, bill_id=10, filename="r1.pdf", storage_key="b/bill/r1.pdf"),
        Receipt(id=2, bill_id=10, filename="r2.pdf", storage_key="b/bill/r2.pdf"),
    ]
    svc, job, _, receipt_repo = _make_service(receipts_by_bill={10: receipts})
    actor = _actor()

    svc.enqueue_bill_delete_cascade(actor, bill)

    receipt_repo.list_by_bill.assert_called_once_with(10)
    keys = [call.args[2]["key"] for call in job.enqueue_for.call_args_list]
    assert keys == ["b/bill/r1.pdf", "b/bill/r2.pdf", "b/bill.pdf"]
    for call in job.enqueue_for.call_args_list:
        assert call.args[0] is actor
        assert call.args[1] == "s3.delete"


def test_enqueue_bill_delete_cascade_includes_recibo_pdf():
    bill = Bill(
        id=10,
        uuid="bill-u",
        billing_id=1,
        reference_month="2025-03",
        pdf_path="b/bill.pdf",
        recibo_pdf_path="b/bill.recibo.pdf",
    )
    svc, job, _, _ = _make_service(receipts_by_bill={10: []})

    svc.enqueue_bill_delete_cascade(_actor(), bill)

    keys = [call.args[2]["key"] for call in job.enqueue_for.call_args_list]
    assert keys == ["b/bill.pdf", "b/bill.recibo.pdf"]


def test_enqueue_bill_delete_cascade_skips_empty_pdf_path():
    bill = Bill(id=10, uuid="u", billing_id=1, reference_month="2025-03", pdf_path="")
    svc, job, _, _ = _make_service(
        receipts_by_bill={
            10: [
                Receipt(id=1, bill_id=10, filename="r.pdf", storage_key="b/bill/r.pdf"),
            ]
        }
    )

    svc.enqueue_bill_delete_cascade(_actor(), bill)

    keys = [call.args[2]["key"] for call in job.enqueue_for.call_args_list]
    assert keys == ["b/bill/r.pdf"]


def test_enqueue_bill_delete_cascade_handles_bill_id_none():
    bill = Bill(id=None, uuid="u", billing_id=1, reference_month="2025-03", pdf_path="b/bill.pdf")
    svc, job, _, receipt_repo = _make_service()

    svc.enqueue_bill_delete_cascade(_actor(), bill)

    receipt_repo.list_by_bill.assert_not_called()
    keys = [call.args[2]["key"] for call in job.enqueue_for.call_args_list]
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
    actor = _actor()

    svc.enqueue_billing_delete_cascade(actor, billing)

    bill_repo.list_by_billing.assert_called_once_with(99)
    keys = [call.args[2]["key"] for call in job.enqueue_for.call_args_list]
    assert keys == [
        "b/b1/r1.pdf",
        "b/b1.pdf",
        "b/b2/r1.pdf",
        "b/b2/r2.pdf",
        "b/b2.pdf",
    ]
    for call in job.enqueue_for.call_args_list:
        assert call.args[0] is actor


def test_enqueue_billing_delete_cascade_billing_id_none_is_noop():
    billing = Billing(id=None, uuid="u", name="Apt")
    svc, job, bill_repo, _ = _make_service()

    svc.enqueue_billing_delete_cascade(_actor(), billing)

    bill_repo.list_by_billing.assert_not_called()
    job.enqueue_for.assert_not_called()


def test_enqueue_billing_delete_cascade_with_no_bills_is_noop():
    billing = Billing(id=99, uuid="u", name="Apt")
    svc, job, bill_repo, _ = _make_service(bills=[])

    svc.enqueue_billing_delete_cascade(_actor(), billing)

    bill_repo.list_by_billing.assert_called_once_with(99)
    job.enqueue_for.assert_not_called()


def test_billing_cascade_enqueues_attachment_keys():
    from rentivo.models.billing_attachment import BillingAttachment

    attachment = BillingAttachment(
        id=1,
        billing_id=3,
        name="c",
        filename="c.pdf",
        storage_key="b-uuid/attachments/x.pdf",
        content_type="application/pdf",
        file_size=1,
    )
    svc, job, bill_repo, _ = _make_service(bills=[], attachments=[attachment])

    svc.enqueue_billing_delete_cascade(_actor(), Billing(id=3, uuid="b-uuid", name="A", items=[]))

    keys = [c.args[2]["key"] for c in job.enqueue_for.call_args_list]
    assert keys == ["b-uuid/attachments/x.pdf"]


def test_enqueue_attachment_delete():
    from rentivo.models.billing_attachment import BillingAttachment

    svc, job, _, _ = _make_service()
    actor = _actor()
    svc.enqueue_attachment_delete(
        actor,
        BillingAttachment(id=1, billing_id=1, name="n", filename="f.pdf", storage_key="k.pdf"),
    )
    job.enqueue_for.assert_called_once_with(actor, "s3.delete", {"key": "k.pdf"})
