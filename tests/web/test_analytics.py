"""Unit tests for web/analytics.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from web import analytics


@pytest.fixture
def mock_request():
    req = MagicMock()
    req.session = {}
    req.state = MagicMock()
    req.state.request_id = "01H00000000000000000000000"
    return req


# --- analytics_hash ---


class TestAnalyticsHash:
    def test_none_returns_none(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        assert analytics.analytics_hash(None) is None

    def test_empty_string_returns_none(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        assert analytics.analytics_hash("") is None

    def test_returns_16_hex_chars(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        h = analytics.analytics_hash(42)
        assert isinstance(h, str)
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        assert analytics.analytics_hash(42) == analytics.analytics_hash(42)
        assert analytics.analytics_hash("hello") == analytics.analytics_hash("hello")

    def test_different_inputs_differ(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        assert analytics.analytics_hash(1) != analytics.analytics_hash(2)

    def test_different_secret_keys_produce_different_hashes(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "secret_key", "secret-A")
        h1 = analytics.analytics_hash(42)
        monkeypatch.setattr(analytics.settings, "secret_key", "secret-B")
        h2 = analytics.analytics_hash(42)
        assert h1 != h2

    def test_accepts_int_and_str(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        assert analytics.analytics_hash(42) == analytics.analytics_hash("42")


# --- build_page_context ---


class TestBuildPageContext:
    def test_returns_none_when_gtm_disabled(self, mock_request, monkeypatch):
        monkeypatch.setattr(analytics.settings, "gtm_container_id", "")
        assert analytics.build_page_context(mock_request, "billing/list.html", {}) is None

    def test_anonymous_user(self, mock_request, monkeypatch):
        monkeypatch.setattr(analytics.settings, "gtm_container_id", "GTM-TEST")
        monkeypatch.setattr(analytics.settings, "environment", "production")
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        mock_request.session = {}
        ctx = analytics.build_page_context(mock_request, "login.html", {"asset_version": "abc123"})
        assert ctx["event"] == "page_context"
        assert ctx["user_status"] == "anonymous"
        assert ctx["user_id_hash"] is None
        assert ctx["page_type"] == "auth"
        assert ctx["page_section"] == "root"
        assert ctx["page_template"] == "login"
        assert ctx["locale"] == "pt-BR"
        assert ctx["environment"] == "production"
        assert ctx["app_version"] == "abc123"

    def test_authenticated_user(self, mock_request, monkeypatch):
        monkeypatch.setattr(analytics.settings, "gtm_container_id", "GTM-TEST")
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        mock_request.session = {"user_id": 42, "username": "alice"}
        ctx = analytics.build_page_context(mock_request, "billing/list.html", {})
        assert ctx["user_status"] == "authenticated"
        assert ctx["user_id_hash"] is not None
        assert len(ctx["user_id_hash"]) == 16
        assert ctx["page_type"] == "list"
        assert ctx["page_section"] == "billing"
        assert ctx["page_template"] == "billing/list"

    def test_page_type_inference(self, mock_request, monkeypatch):
        monkeypatch.setattr(analytics.settings, "gtm_container_id", "GTM-TEST")
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        cases = [
            ("billing/list.html", "list"),
            ("billing/detail.html", "detail"),
            ("billing/create.html", "form"),
            ("billing/edit.html", "form"),
            ("bill/generate.html", "form"),
            ("bill/detail.html", "detail"),
            ("bill/edit.html", "form"),
            ("login.html", "auth"),
            ("signup.html", "auth"),
            ("mfa_verify.html", "auth"),
            ("404.html", "error"),
            ("landing.html", "landing"),
            ("security/index.html", "dashboard"),
            ("unknown.html", "other"),
        ]
        for template, expected in cases:
            ctx = analytics.build_page_context(mock_request, template, {})
            assert ctx["page_type"] == expected, f"{template} -> expected {expected}, got {ctx['page_type']}"

    def test_page_type_suffix_fallbacks(self, mock_request, monkeypatch):
        """Templates outside PAGE_TYPE_MAP still classify by naming suffix."""
        monkeypatch.setattr(analytics.settings, "gtm_container_id", "GTM-TEST")
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        cases = [
            ("future/create.html", "form"),
            ("future/edit.html", "form"),
            ("future/generate.html", "form"),
            ("future/list.html", "list"),
            ("future/detail.html", "detail"),
        ]
        for template, expected in cases:
            ctx = analytics.build_page_context(mock_request, template, {})
            assert ctx["page_type"] == expected, f"{template} -> expected {expected}, got {ctx['page_type']}"

    def test_does_not_include_raw_username_or_email(self, mock_request, monkeypatch):
        monkeypatch.setattr(analytics.settings, "gtm_container_id", "GTM-TEST")
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        mock_request.session = {
            "user_id": 99,
            "username": "alice",
            "email": "alice@example.com",
        }
        ctx = analytics.build_page_context(mock_request, "billing/list.html", {})
        import json

        serialized = json.dumps(ctx)
        assert "alice" not in serialized
        assert "example.com" not in serialized

    def test_request_id_included_when_present(self, mock_request, monkeypatch):
        monkeypatch.setattr(analytics.settings, "gtm_container_id", "GTM-TEST")
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        mock_request.state.request_id = "01H12345678"
        ctx = analytics.build_page_context(mock_request, "billing/list.html", {})
        assert ctx["request_id"] == "01H12345678"

    def test_request_id_none_when_state_missing(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "gtm_container_id", "GTM-TEST")
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        req = MagicMock()
        req.session = {}

        # Fresh state mock with no request_id attribute
        class StateNoRid:
            pass

        req.state = StateNoRid()
        ctx = analytics.build_page_context(req, "billing/list.html", {})
        assert ctx["request_id"] is None


# --- push_event / pop_events ---


class TestPushPopEvents:
    def test_push_noop_when_gtm_disabled(self, mock_request, monkeypatch):
        monkeypatch.setattr(analytics.settings, "gtm_container_id", "")
        mock_request.session = {}
        analytics.push_event(mock_request, {"event": "foo"})
        assert mock_request.session == {}

    def test_push_appends_event(self, mock_request, monkeypatch):
        monkeypatch.setattr(analytics.settings, "gtm_container_id", "GTM-TEST")
        mock_request.session = {}
        analytics.push_event(mock_request, {"event": "foo"})
        analytics.push_event(mock_request, {"event": "bar"})
        assert mock_request.session[analytics.SESSION_KEY] == [
            {"event": "foo"},
            {"event": "bar"},
        ]

    def test_pop_empty_when_none_pushed(self, mock_request):
        mock_request.session = {}
        assert analytics.pop_events(mock_request) == []

    def test_pop_drains_and_empties(self, mock_request, monkeypatch):
        monkeypatch.setattr(analytics.settings, "gtm_container_id", "GTM-TEST")
        mock_request.session = {}
        analytics.push_event(mock_request, {"event": "foo"})
        analytics.push_event(mock_request, {"event": "bar"})
        events = analytics.pop_events(mock_request)
        assert events == [{"event": "foo"}, {"event": "bar"}]
        assert analytics.SESSION_KEY not in mock_request.session

    def test_pop_works_even_when_gtm_disabled(self, mock_request, monkeypatch):
        """Safety: if GTM was enabled, events were queued, then GTM got disabled, pop still drains."""
        mock_request.session = {analytics.SESSION_KEY: [{"event": "foo"}]}
        monkeypatch.setattr(analytics.settings, "gtm_container_id", "")
        assert analytics.pop_events(mock_request) == [{"event": "foo"}]
