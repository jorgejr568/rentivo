from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from rentivo.whatsapp import (
    build_invoice_message,
    build_whatsapp_link,
    normalize_wa_phone,
)


class TestNormalizeWaPhone:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("+55 11 99999-8888", "5511999998888"),  # punctuation stripped
            ("11999998888", "5511999998888"),  # 11-digit national mobile -> +55
            ("1133224455", "551133224455"),  # 10-digit national landline -> +55
            ("5511999998888", "5511999998888"),  # already international, kept
            ("(11) 99999-8888", "5511999998888"),  # parens/space/dash
            ("+1 415 555 2671", "14155552671"),  # non-BR international kept
        ],
    )
    def test_normalizes_valid_numbers(self, raw, expected):
        assert normalize_wa_phone(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   ", "abc", "+55", "123", "0" * 20])
    def test_rejects_unusable_numbers(self, raw):
        assert normalize_wa_phone(raw) is None


class TestBuildInvoiceMessage:
    def test_includes_essentials_and_pix(self):
        msg = build_invoice_message(
            billing_name="Apt 101",
            reference_month="2025-03",
            amount_centavos=285000,
            due_date="10/04/2025",
            pix_payload="00020126...6304ABCD",
        )
        assert "Apt 101" in msg
        assert "Março/2025" in msg
        assert "R$ 2.850,00" in msg
        assert "10/04/2025" in msg
        assert "00020126...6304ABCD" in msg
        assert "copia e cola" in msg.lower()

    def test_omits_due_date_line_when_absent(self):
        msg = build_invoice_message(
            billing_name="Apt 101",
            reference_month="2025-03",
            amount_centavos=285000,
            due_date=None,
            pix_payload="PIXPAYLOAD",
        )
        assert "Vencimento" not in msg
        assert "PIXPAYLOAD" in msg


class TestBuildWhatsappLink:
    def test_builds_url_encoded_deep_link(self):
        link = build_whatsapp_link("+55 11 99999-8888", "olá mundo & cia")
        parsed = urlparse(link)
        assert parsed.scheme == "https"
        assert parsed.netloc == "wa.me"
        assert parsed.path == "/5511999998888"
        assert parse_qs(parsed.query)["text"] == ["olá mundo & cia"]

    def test_returns_none_for_unusable_phone(self):
        assert build_whatsapp_link("", "msg") is None
        assert build_whatsapp_link(None, "msg") is None
