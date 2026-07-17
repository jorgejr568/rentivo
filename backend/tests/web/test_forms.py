from legacy_web.forms import (
    parse_brl,
    parse_extras,
    parse_formset,
    parse_line_items,
    safe_redirect_path,
)
from rentivo.models.billing import ItemType


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

    def test_non_numeric_total_forms(self):
        form_data = {"items-TOTAL_FORMS": "abc"}
        rows = parse_formset(form_data, "items")
        assert rows == []

    def test_none_total_forms(self):
        form_data = {"items-TOTAL_FORMS": None}
        rows = parse_formset(form_data, "items")
        assert rows == []


class TestSafeRedirectPath:
    FALLBACK = "/billings/x/bills/y/edit"

    def test_relative_path_is_kept(self):
        assert safe_redirect_path("/billings/abc/bills/def/edit", self.FALLBACK) == "/billings/abc/bills/def/edit"

    def test_empty_falls_back(self):
        assert safe_redirect_path("", self.FALLBACK) == self.FALLBACK

    def test_whitespace_falls_back(self):
        assert safe_redirect_path("   ", self.FALLBACK) == self.FALLBACK

    def test_absolute_https_rejected(self):
        assert safe_redirect_path("https://evil.example/login", self.FALLBACK) == self.FALLBACK

    def test_absolute_http_rejected(self):
        assert safe_redirect_path("http://evil.example/", self.FALLBACK) == self.FALLBACK

    def test_protocol_relative_rejected(self):
        assert safe_redirect_path("//evil.example/path", self.FALLBACK) == self.FALLBACK

    def test_backslash_rejected(self):
        assert safe_redirect_path("/\\evil.example/path", self.FALLBACK) == self.FALLBACK

    def test_encoded_slash_rejected(self):
        assert safe_redirect_path("/%2fevil.example", self.FALLBACK) == self.FALLBACK

    def test_no_leading_slash_rejected(self):
        assert safe_redirect_path("billings/abc", self.FALLBACK) == self.FALLBACK


class TestParseLineItems:
    def test_basic_parsing(self):
        form_data = {
            "items-TOTAL_FORMS": "2",
            "items-0-description": "Aluguel",
            "items-0-amount": "1000,00",
            "items-0-item_type": "fixed",
            "items-1-description": "Taxa",
            "items-1-amount": "50,00",
            "items-1-item_type": "extra",
        }
        items = parse_line_items(form_data, "items")
        assert len(items) == 2
        assert items[0].description == "Aluguel"
        assert items[0].amount == 100000
        assert items[0].item_type == ItemType.FIXED
        assert items[0].index == 0
        assert items[1].item_type == ItemType.EXTRA
        assert items[1].index == 1

    def test_skips_blank_description_but_preserves_index(self):
        form_data = {
            "items-TOTAL_FORMS": "2",
            "items-0-description": "   ",
            "items-0-amount": "100",
            "items-0-item_type": "fixed",
            "items-1-description": "Rent",
            "items-1-amount": "100",
            "items-1-item_type": "fixed",
        }
        items = parse_line_items(form_data, "items")
        assert len(items) == 1
        assert items[0].description == "Rent"
        assert items[0].index == 1  # formset position kept for sort_order

    def test_invalid_item_type_falls_back_to_fixed(self):
        form_data = {
            "items-TOTAL_FORMS": "1",
            "items-0-description": "Rent",
            "items-0-amount": "100",
            "items-0-item_type": "bogus",
        }
        items = parse_line_items(form_data, "items")
        assert items[0].item_type == ItemType.FIXED

    def test_missing_item_type_defaults_to_fixed(self):
        form_data = {
            "items-TOTAL_FORMS": "1",
            "items-0-description": "Rent",
            "items-0-amount": "100",
        }
        items = parse_line_items(form_data, "items")
        assert items[0].item_type == ItemType.FIXED

    def test_invalid_amount_defaults_to_zero(self):
        form_data = {
            "items-TOTAL_FORMS": "1",
            "items-0-description": "Rent",
            "items-0-amount": "abc",
            "items-0-item_type": "fixed",
        }
        items = parse_line_items(form_data, "items")
        assert items[0].amount == 0

    def test_amount_only_for_fixed_zeroes_variable_amount(self):
        form_data = {
            "items-TOTAL_FORMS": "2",
            "items-0-description": "Water",
            "items-0-amount": "50,00",
            "items-0-item_type": "variable",
            "items-1-description": "Rent",
            "items-1-amount": "1000,00",
            "items-1-item_type": "fixed",
        }
        items = parse_line_items(form_data, "items", amount_only_for_fixed=True)
        assert items[0].amount == 0
        assert items[1].amount == 100000

    def test_variable_amount_parsed_when_flag_off(self):
        form_data = {
            "items-TOTAL_FORMS": "1",
            "items-0-description": "Water",
            "items-0-amount": "50,00",
            "items-0-item_type": "variable",
        }
        items = parse_line_items(form_data, "items")
        assert items[0].amount == 5000


class TestParseExtras:
    def test_basic_parsing(self):
        form_data = {
            "extras-TOTAL_FORMS": "1",
            "extras-0-description": "Reparo",
            "extras-0-amount": "50,00",
        }
        assert parse_extras(form_data) == [("Reparo", 5000)]

    def test_skips_blank_description(self):
        form_data = {
            "extras-TOTAL_FORMS": "1",
            "extras-0-description": "  ",
            "extras-0-amount": "50,00",
        }
        assert parse_extras(form_data) == []

    def test_skips_zero_amount(self):
        form_data = {
            "extras-TOTAL_FORMS": "1",
            "extras-0-description": "Reparo",
            "extras-0-amount": "0",
        }
        assert parse_extras(form_data) == []

    def test_skips_invalid_amount(self):
        form_data = {
            "extras-TOTAL_FORMS": "1",
            "extras-0-description": "Reparo",
            "extras-0-amount": "not-a-number",
        }
        assert parse_extras(form_data) == []

    def test_custom_prefix(self):
        form_data = {
            "stuff-TOTAL_FORMS": "1",
            "stuff-0-description": "X",
            "stuff-0-amount": "1,00",
        }
        assert parse_extras(form_data, prefix="stuff") == [("X", 100)]
