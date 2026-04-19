from web.forms import parse_brl, parse_formset, safe_redirect_path


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
