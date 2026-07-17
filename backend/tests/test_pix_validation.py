"""Tests for PIX key validation/normalization."""

from __future__ import annotations

import pytest

from rentivo.pix import classify_pix_key, validate_pix_key


class TestClassifyPixKey:
    @pytest.mark.parametrize(
        "key,kind",
        [
            ("12345678901", "cpf"),
            ("12345678000190", "cnpj"),
            ("user@example.com", "email"),
            ("+5511987654321", "phone"),
            ("+551198765432", "phone"),
            ("123e4567-e89b-12d3-a456-426614174000", "evp"),
        ],
    )
    def test_recognized(self, key, kind):
        assert classify_pix_key(key) == kind

    @pytest.mark.parametrize(
        "key",
        [
            "",
            "not-a-key",
            "1234",
            "user@",
            "@example.com",
            "+1 555 1234567",  # non-BR country code
            "abcd-1234",
        ],
    )
    def test_rejected(self, key):
        assert classify_pix_key(key) is None


class TestValidatePixKey:
    def test_cpf_strips_punctuation(self):
        assert validate_pix_key("123.456.789-01") == "12345678901"

    def test_cnpj_strips_punctuation(self):
        assert validate_pix_key("12.345.678/0001-90") == "12345678000190"

    def test_phone_landline_prefixes_br_country_code(self):
        # 10 digits with DDD → Brazilian landline, not a CPF
        assert validate_pix_key("1133334444") == "+551133334444"

    def test_phone_with_country_code(self):
        assert validate_pix_key("+5511987654321") == "+5511987654321"

    def test_eleven_digits_treated_as_cpf(self):
        # 11 digits is ambiguous; CPF wins. Users wanting a mobile phone must
        # include the +55 country code.
        assert validate_pix_key("11987654321") == "11987654321"

    def test_email_lowercased(self):
        assert validate_pix_key("User@Example.com") == "user@example.com"

    def test_evp_lowercased(self):
        raw = "123E4567-E89B-12D3-A456-426614174000"
        assert validate_pix_key(raw) == raw.lower()

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            validate_pix_key("")

    def test_whitespace_raises(self):
        with pytest.raises(ValueError):
            validate_pix_key("   ")

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            validate_pix_key("not-a-pix-key")
