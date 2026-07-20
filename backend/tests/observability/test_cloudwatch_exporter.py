from botocore.credentials import Credentials

from rentivo.observability import tracing


class _PreparedRequest:
    """Minimal stand-in for a requests.PreparedRequest."""

    def __init__(self):
        self.method = "POST"
        self.url = "https://xray.us-east-1.amazonaws.com/v1/traces"
        self.body = b"\x0a\x00"
        self.headers = {"Content-Type": "application/x-protobuf"}


def test_sigv4_auth_signs_request_for_xray():
    auth = tracing._make_sigv4_auth(Credentials("AKIAEXAMPLE", "secret"), "us-east-1")
    req = _PreparedRequest()
    auth(req)
    authz = req.headers["Authorization"]
    assert authz.startswith("AWS4-HMAC-SHA256")
    assert "/us-east-1/xray/aws4_request" in authz
    assert "X-Amz-Date" in req.headers
    # static creds carry no session token, so this header must be absent
    assert "X-Amz-Security-Token" not in req.headers


def test_aws_credentials_explicit(monkeypatch):
    monkeypatch.setattr(tracing.settings, "otel_aws_access_key_id", "AKIAEXPLICIT")
    monkeypatch.setattr(tracing.settings, "otel_aws_secret_access_key", "shh")
    creds = tracing._aws_credentials()
    assert creds.access_key == "AKIAEXPLICIT"


def test_aws_credentials_falls_back_to_default_chain(monkeypatch):
    monkeypatch.setattr(tracing.settings, "otel_aws_access_key_id", "")
    monkeypatch.setattr(tracing.settings, "otel_aws_secret_access_key", "")
    # Returns whatever the ambient AWS chain finds (often None in CI) — just
    # exercise the branch without raising.
    creds = tracing._aws_credentials()
    assert creds is None or hasattr(creds, "access_key")


def test_configure_cloudwatch_builds_xray_provider(monkeypatch):
    from opentelemetry.sdk.extension.aws.trace import AwsXRayIdGenerator

    monkeypatch.setattr(tracing.settings, "otel_enabled", True)
    monkeypatch.setattr(tracing.settings, "otel_exporter", "cloudwatch")
    monkeypatch.setattr(tracing.settings, "otel_aws_region", "us-east-1")
    monkeypatch.setattr(tracing.settings, "otel_aws_access_key_id", "AKIAEXAMPLE")
    monkeypatch.setattr(tracing.settings, "otel_aws_secret_access_key", "secret")

    tracing.configure_tracing()
    try:
        assert tracing.tracing_enabled()
        assert isinstance(tracing._provider.id_generator, AwsXRayIdGenerator)
    finally:
        tracing.shutdown_tracing()
