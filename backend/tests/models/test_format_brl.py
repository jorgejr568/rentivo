from rentivo.models import format_brl, parse_brl


class TestFormatBrl:
    def test_zero(self):
        assert format_brl(0) == "R$ 0,00"

    def test_small_value(self):
        assert format_brl(150) == "R$ 1,50"

    def test_exact_reais(self):
        assert format_brl(10000) == "R$ 100,00"

    def test_thousands_separator(self):
        assert format_brl(285000) == "R$ 2.850,00"

    def test_large_value(self):
        assert format_brl(1500000) == "R$ 15.000,00"

    def test_single_centavo(self):
        assert format_brl(1) == "R$ 0,01"


class TestParseBrl:
    def test_plain_integer(self):
        assert parse_brl("2850") == 285000

    def test_decimal_dot(self):
        assert parse_brl("2850.00") == 285000

    def test_br_format(self):
        assert parse_brl("2.850,00") == 285000

    def test_decimal_comma(self):
        assert parse_brl("2850,50") == 285050

    def test_empty_string(self):
        assert parse_brl("") is None

    def test_whitespace(self):
        assert parse_brl("   ") is None

    def test_invalid_text(self):
        assert parse_brl("abc") is None

    def test_with_leading_whitespace(self):
        assert parse_brl("  100  ") == 10000

    def test_small_value(self):
        assert parse_brl("1.50") == 150

    def test_zero(self):
        assert parse_brl("0") == 0
