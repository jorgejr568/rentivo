import json

import pytest

from rentivo.pii_redaction import redact

API_KEY = "rntv-v1-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789_-abc"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authorization", f"Bearer {API_KEY}"),
        ("Authorization", f"Bearer {API_KEY}"),
        ("cookie", f"__Host-rentivo_access={API_KEY}"),
        ("Cookie", f"__Host-rentivo_access={API_KEY}"),
        ("secret", API_KEY),
        ("secret_hash", "0123456789abcdef" * 4),
    ],
)
def test_api_key_fields_are_redacted_case_insensitively(field, value):
    assert redact({field: value}) == {field: "[REDACTED]"}


def test_api_key_material_is_redacted_recursively_even_under_a_benign_field():
    payload = {
        "event": "request.failed",
        "details": [
            {"message": API_KEY},
            {"request": {"authorization": f"Bearer {API_KEY}"}},
            {"safe": "preserved"},
        ],
    }

    redacted = redact(payload)

    assert redacted == {
        "event": "request.failed",
        "details": [
            {"message": "[REDACTED]"},
            {"request": {"authorization": "[REDACTED]"}},
            {"safe": "preserved"},
        ],
    }
    assert API_KEY not in json.dumps(redacted)


def test_api_key_material_is_redacted_inside_tuples():
    assert redact(("safe", API_KEY)) == ("safe", "[REDACTED]")


@pytest.mark.parametrize(
    "field",
    [
        "password",
        "passwordConfirmation",
        "password_hash",
        "accessToken",
        "refresh_token",
        "apiKeySecret",
        "api_key_hash",
        "csrfToken",
        "challenge_token",
        "oauthCode",
        "login_token",
        "passwordResetToken",
        "nonce_hash",
        "totpCode",
        "recovery_codes",
        "mfa_code",
        "clientDataJSON",
        "authenticator_data",
        "signature",
        "userHandle",
        "attestationObject",
        "rawId",
        "client_secret",
        "sessionToken",
        "access_credential",
        "aws_secret_access_key",
        "id_token",
        "code_verifier",
    ],
)
def test_credential_field_variants_are_redacted(field):
    assert redact({field: "credential-value"}) == {field: "[REDACTED]"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "OIDC failed: id_token=oidc-secret recovery_code=recovery-secret",
            "OIDC failed: id_token=[REDACTED] recovery_code=[REDACTED]",
        ),
        (
            "request Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret Cookie: session_token=session-secret",
            "request Authorization: Bearer [REDACTED] Cookie: [REDACTED]",
        ),
        (
            'oauth client_secret="client secret" code_verifier=verifier-secret',
            "oauth client_secret=[REDACTED] code_verifier=[REDACTED]",
        ),
        (
            "Cookie: __Host-session=opaque-session-secret; theme=dark",
            "Cookie: [REDACTED]",
        ),
        (
            "Set-Cookie: __Host-rentivo_session=opaque-session-secret; HttpOnly",
            "Set-Cookie: [REDACTED]",
        ),
    ],
)
def test_credential_material_is_redacted_inside_arbitrary_strings(value, expected):
    assert redact(value) == expected


def test_embedded_credential_redaction_is_idempotent():
    value = "id_token=[REDACTED] Cookie: [REDACTED]"

    assert redact(redact(value)) == redact(value)


def test_safe_reference_and_observability_fields_are_preserved():
    safe = {
        "api_key_uuid": "01SAFEKEYUUID",
        "api_key_class": "integration",
        "key_hint": "rntv-v1-abcd...yz",
        "key_start": "abcd",
        "key_end": "yz",
        "request_id": "request-123",
        "analytics_event": "login_success",
    }

    assert redact(safe) == safe
