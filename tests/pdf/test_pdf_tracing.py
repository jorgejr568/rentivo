from rentivo.pdf import merger


def test_merge_receipts_emits_span(span_exporter):
    # No receipts → returns the input unchanged without touching pypdf internals.
    invoice = b"%PDF-1.4 minimal"
    out, failed = merger.merge_receipts(invoice, [])
    assert failed == []
    assert "pdf.merge_receipts" in [s.name for s in span_exporter.get_finished_spans()]
