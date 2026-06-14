from rentivo.encryption.base64 import Base64Backend


def test_per_field_not_spanned_batch_is(span_exporter):
    # base64 encrypt/decrypt are not spanned; the batch decrypt_many (inherited
    # from the base backend) is the single traced layer, carrying a count.
    b = Base64Backend()
    token = b.encrypt("secret")
    b.decrypt(token)
    b.decrypt_many([token, token, token])
    finished = span_exporter.get_finished_spans()
    names = [s.name for s in finished]
    assert names == ["encryption.decrypt_many"]
    assert finished[0].attributes["count"] == 3


def test_base64_disabled_still_works():
    # No span_exporter → tracing off. Plumbing must be unaffected.
    b = Base64Backend()
    token = b.encrypt("secret")
    assert token != "secret"
    assert b.decrypt(token) == "secret"
