"""Unit tests for the shared analytics hash helper."""

from __future__ import annotations

from rentivo import analytics


class TestAnalyticsHash:
    def test_none_returns_none(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        assert analytics.analytics_hash(None) is None

    def test_empty_string_returns_none(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        assert analytics.analytics_hash("") is None

    def test_returns_16_hex_chars(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        hashed = analytics.analytics_hash(42)
        assert isinstance(hashed, str)
        assert len(hashed) == 16
        assert all(char in "0123456789abcdef" for char in hashed)

    def test_deterministic(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        assert analytics.analytics_hash(42) == analytics.analytics_hash(42)
        assert analytics.analytics_hash("hello") == analytics.analytics_hash("hello")

    def test_different_inputs_differ(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        assert analytics.analytics_hash(1) != analytics.analytics_hash(2)

    def test_different_secret_keys_produce_different_hashes(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "secret_key", "secret-A")
        first_hash = analytics.analytics_hash(42)
        monkeypatch.setattr(analytics.settings, "secret_key", "secret-B")
        second_hash = analytics.analytics_hash(42)
        assert first_hash != second_hash

    def test_accepts_int_and_str(self, monkeypatch):
        monkeypatch.setattr(analytics.settings, "secret_key", "test-secret")
        assert analytics.analytics_hash(42) == analytics.analytics_hash("42")
