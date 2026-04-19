"""Regression tests for parse_brl Decimal-based rounding."""

from __future__ import annotations

from rentivo.models import parse_brl


class TestParseBrlRounding:
    def test_integer(self):
        assert parse_brl("2850") == 285000

    def test_brl_format(self):
        assert parse_brl("2.850,00") == 285000

    def test_dot_format(self):
        assert parse_brl("2850.00") == 285000

    def test_half_up_not_banker(self):
        # banker's rounding would give 2 here; we want 2 (round half up)
        assert parse_brl("0,015") == 2
        # 0.025 -> 3 centavos under half-up, 2 under banker's
        assert parse_brl("0,025") == 3

    def test_empty(self):
        assert parse_brl("") is None

    def test_invalid(self):
        assert parse_brl("abc") is None

    def test_negative_rejected(self):
        assert parse_brl("-2850,00") is None

    def test_half_up_rounds_up_not_zero(self):
        # 0.005 -> 1 centavo under half-up, 0 under banker's
        assert parse_brl("0,005") == 1

    def test_whitespace_only(self):
        assert parse_brl("   ") is None

    def test_large_amount(self):
        assert parse_brl("1.234.567,89") == 123456789
