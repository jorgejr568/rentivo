import base64

from rentivo.encryption.kms import KMSBackend


class _FakeKMSClient:
    def encrypt(self, KeyId, Plaintext):
        return {"CiphertextBlob": b"BLOB"}

    def decrypt(self, CiphertextBlob, KeyId):
        return {"Plaintext": b"secret"}


def _backend():
    b = KMSBackend.__new__(KMSBackend)
    b.key_id = "alias/test"
    b.client = _FakeKMSClient()
    return b


def test_encrypt_decrypt_emit_spans(span_exporter):
    b = _backend()
    token = b.encrypt("secret")
    b.decrypt(token)
    b.decrypt_many([token, token])
    names = [s.name for s in span_exporter.get_finished_spans()]
    assert "kms.encrypt" in names
    assert "kms.decrypt" in names
    assert "kms.decrypt_many" in names


def test_kms_disabled_still_works():
    # No span_exporter → tracing off. Plumbing must be unaffected.
    b = _backend()
    token = b.encrypt("secret")
    assert b.decrypt(token) == "secret"
    assert base64.b64decode(token[len("enc:v1:") :]) == b"BLOB"
