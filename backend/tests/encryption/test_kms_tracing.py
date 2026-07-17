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


def test_only_batch_decrypt_is_spanned(span_exporter):
    # Per-field encrypt/decrypt are intentionally not spanned; only the batch
    # decrypt_many emits one span (with a count) to avoid span explosion.
    b = _backend()
    token = b.encrypt("secret")
    b.decrypt(token)
    b.decrypt_many([token, token])
    finished = span_exporter.get_finished_spans()
    names = [s.name for s in finished]
    assert names == ["kms.decrypt_many"]
    assert finished[0].attributes["count"] == 2


def test_kms_disabled_still_works():
    # No span_exporter → tracing off. Plumbing must be unaffected.
    b = _backend()
    token = b.encrypt("secret")
    assert b.decrypt(token) == "secret"
    assert base64.b64decode(token[len("enc:v1:") :]) == b"BLOB"
