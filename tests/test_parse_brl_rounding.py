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

    def test_negative_allowed(self):
        assert parse_brl("-2850,00") == -285000
