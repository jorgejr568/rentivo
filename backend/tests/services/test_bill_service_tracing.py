from rentivo.services.bill_service import BillService


class _FakeStorage:
    def save(self, key, data, content_type="application/pdf"):
        return key

    def get(self, key):
        raise AssertionError("no receipts in this test")


class _FakeBillRepo:
    def update_pdf_path(self, bill_id, path):
        pass

    def update_pdf_render_status(self, bill_id, status):
        pass


def test_render_pdf_sync_nests_pdf_and_storage_spans(span_exporter, sample_billing, sample_bill):
    # sample_billing / sample_bill come from tests/conftest.py.
    billing = sample_billing()
    bill = sample_bill()
    bill.id = 1
    bill.total_amount = 1000

    class _Pix:
        def resolve_for_billing(self, b):
            from rentivo.services.pix_service import PixConfig

            return PixConfig(pix_key="k@pix", merchant_name="M", merchant_city="C")

    svc = BillService(_FakeBillRepo(), _FakeStorage(), pix_service=_Pix())
    svc._render_pdf_sync(bill, billing)

    names = {s.name for s in span_exporter.get_finished_spans()}
    assert "bill.render_pdf_sync" in names
    assert "pdf.generate" in names
    assert "s3.save" not in names  # local fake storage isn't S3
    # pdf.generate must be a child of bill.render_pdf_sync
    finished = {s.name: s for s in span_exporter.get_finished_spans()}
    assert finished["pdf.generate"].parent.span_id == finished["bill.render_pdf_sync"].context.span_id
