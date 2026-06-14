from rentivo.storage.local import LocalStorage


def test_save_get_url_delete_emit_spans(span_exporter, tmp_path):
    s = LocalStorage(str(tmp_path))
    s.save("a/b.pdf", b"data")
    s.get("a/b.pdf")
    s.get_url("a/b.pdf")
    s.delete("a/b.pdf")
    names = [span.name for span in span_exporter.get_finished_spans()]
    assert "local.save" in names
    assert "local.get" in names
    assert "local.get_url" in names
    assert "local.delete" in names


def test_local_disabled_still_works(tmp_path):
    # No span_exporter → tracing off. Plumbing must be unaffected.
    s = LocalStorage(str(tmp_path))
    s.save("a/b.pdf", b"data")
    assert s.get("a/b.pdf") == b"data"
    s.delete("a/b.pdf")
