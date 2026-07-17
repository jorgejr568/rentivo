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
