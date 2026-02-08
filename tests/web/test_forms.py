from web.forms import parse_brl, parse_formset


class TestParseBrlReexport:
    def test_reexport_works(self):
        assert parse_brl("100") == 10000


class TestParseFormset:
    def test_basic_parsing(self):
        form_data = {
            "items-TOTAL_FORMS": "2",
            "items-0-description": "Rent",
            "items-0-amount": "1000",
            "items-1-description": "Water",
            "items-1-amount": "50",
        }
        rows = parse_formset(form_data, "items")
        assert len(rows) == 2
        assert rows[0]["description"] == "Rent"
        assert rows[1]["amount"] == "50"

    def test_empty_formset(self):
        form_data = {"items-TOTAL_FORMS": "0"}
        rows = parse_formset(form_data, "items")
        assert rows == []

    def test_missing_total_forms(self):
        rows = parse_formset({}, "items")
        assert rows == []

    def test_skips_empty_rows(self):
        form_data = {
            "items-TOTAL_FORMS": "2",
            "items-0-description": "Rent",
            # items-1 has no fields
        }
        rows = parse_formset(form_data, "items")
        assert len(rows) == 1
