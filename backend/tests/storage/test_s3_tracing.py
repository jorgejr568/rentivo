from rentivo.storage.s3 import S3Storage


class _FakeS3Client:
    def put_object(self, **kwargs):
        return {}

    def get_object(self, **kwargs):
        return {"Body": _Body(b"data")}

    def generate_presigned_url(self, *a, **k):
        return "https://example/url"

    def delete_object(self, **kwargs):
        return {}


class _Body:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data


def _backend():
    b = S3Storage.__new__(S3Storage)
    b.bucket = "test-bucket"
    b.presigned_expiry = 60
    b.client = _FakeS3Client()
    return b


def test_s3_methods_emit_spans(span_exporter):
    b = _backend()
    b.save("k", b"data")
    b.get("k")
    b.get_url("k")
    b.delete("k")
    names = [s.name for s in span_exporter.get_finished_spans()]
    assert {"s3.save", "s3.get", "s3.get_url", "s3.delete"} <= set(names)


def test_s3_disabled_still_works():
    b = _backend()
    assert b.save("k", b"data") == "k"
    assert b.get("k") == b"data"
