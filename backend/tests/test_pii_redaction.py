"""Tests for ``rentivo.pii_redaction``."""

from __future__ import annotations

import pytest

from rentivo.pii_redaction import PIIKind, redact


class TestRedactPIX:
    def test_long_value_uses_3_prefix_2_suffix(self):
        assert redact("12345678901", PIIKind.PIX) == "123...01"

    def test_email_shaped_pix_key_uses_pix_mask(self):
        # PIX keys can be emails, but the user requested all PIX-stuff use
        # the same first-3 / last-2 mask regardless of underlying shape.
        assert redact("alice@pix.com", PIIKind.PIX) == "ali...om"

    def test_short_value_collapses_to_stars(self):
        assert redact("Alice", PIIKind.PIX) == "***"
        assert redact("ab", PIIKind.PIX) == "***"
        assert redact("a", PIIKind.PIX) == "***"

    def test_min_length_threshold_is_six(self):
        # 5 chars: prefix(3) + suffix(2) = 5 — would expose the whole value.
        assert redact("abcde", PIIKind.PIX) == "***"
        # 6 chars: hides exactly 1 char — minimum useful mask.
        assert redact("abcdef", PIIKind.PIX) == "abc...ef"

    def test_empty_input_returns_empty(self):
        assert redact("", PIIKind.PIX) == ""

    def test_idempotent_on_typical_input(self):
        # The mask of a long value is itself >=6 chars and matches the
        # first-3 / last-2 pattern — re-applying redact is a no-op.
        once = redact("12345678901", PIIKind.PIX)
        twice = redact(once, PIIKind.PIX)
        assert once == twice == "123...01"


class TestRedactEmail:
    def test_long_local_part(self):
        assert redact("joe@gmail.com", PIIKind.EMAIL) == "jo...@gmail.com"
        assert redact("alice@example.com", PIIKind.EMAIL) == "al...@example.com"

    def test_short_local_part_collapses_to_stars_at(self):
        assert redact("ab@x.co", PIIKind.EMAIL) == "***@x.co"
        assert redact("a@x.co", PIIKind.EMAIL) == "***@x.co"

    def test_three_char_local_uses_2_prefix(self):
        # "abc" → "ab...@x.co". 3 chars hides 1 char — minimum useful mask.
        assert redact("abc@x.co", PIIKind.EMAIL) == "ab...@x.co"

    def test_no_at_sign_falls_back_to_pix_mask(self):
        # Defensive: if a "to_email" field somehow doesn't contain @, treat
        # it as PIX-shaped rather than crashing.
        assert redact("not-an-email", PIIKind.EMAIL) == "not...il"

    def test_empty_input_returns_empty(self):
        assert redact("", PIIKind.EMAIL) == ""

    def test_idempotent_on_typical_input(self):
        once = redact("alice@example.com", PIIKind.EMAIL)
        twice = redact(once, PIIKind.EMAIL)
        assert once == twice == "al...@example.com"


class TestRedactDispatch:
    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="Unknown PII kind"):
            redact("anything", "not-a-kind")  # type: ignore[arg-type]

    def test_kind_is_str_enum(self):
        assert PIIKind.PIX.value == "pix"
        assert PIIKind.EMAIL.value == "email"
