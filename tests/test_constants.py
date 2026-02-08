from landlord.constants import MONTHS_PT, TYPE_LABELS, format_month


class TestMonthsPt:
    def test_all_twelve_months(self):
        assert len(MONTHS_PT) == 12

    def test_january(self):
        assert MONTHS_PT["01"] == "Janeiro"

    def test_december(self):
        assert MONTHS_PT["12"] == "Dezembro"


class TestTypeLabels:
    def test_all_types(self):
        assert set(TYPE_LABELS.keys()) == {"fixed", "variable", "extra"}

    def test_fixed(self):
        assert TYPE_LABELS["fixed"] == "Fixo"


class TestFormatMonth:
    def test_standard(self):
        assert format_month("2025-03") == "Março/2025"

    def test_january(self):
        assert format_month("2024-01") == "Janeiro/2024"

    def test_empty_string(self):
        assert format_month("") == ""

    def test_none(self):
        assert format_month(None) == ""

    def test_no_dash(self):
        assert format_month("202503") == "202503"

    def test_unknown_month(self):
        assert format_month("2025-99") == "99/2025"
