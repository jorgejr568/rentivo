from rentivo.encryption.base64 import Base64Backend


def test_encrypt_decrypt_emit_spans(span_exporter):
    b = Base64Backend()
    token = b.encrypt("secret")
    b.decrypt(token)
    names = [s.name for s in span_exporter.get_finished_spans()]
    assert "base64.encrypt" in names
    assert "base64.decrypt" in names


def test_base64_disabled_still_works():
    # No span_exporter → tracing off. Plumbing must be unaffected.
    b = Base64Backend()
    token = b.encrypt("secret")
    assert token != "secret"
    assert b.decrypt(token) == "secret"
