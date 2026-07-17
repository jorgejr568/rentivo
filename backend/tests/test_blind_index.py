"""Tests for rentivo.blind_index.compute_email_hash."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_cached_key(monkeypatch):
    """Each test starts with a clean key cache."""
    import rentivo.blind_index

    monkeypatch.setattr(rentivo.blind_index, "_cached_key", None)


class TestComputeEmailHash:
    """The HMAC key derives from secret_key — no KMS dependency."""

    def test_is_deterministic_for_same_input(self, monkeypatch):
        monkeypatch.setattr("rentivo.settings.settings.secret_key", "test-secret-1")
        from rentivo.blind_index import compute_email_hash

        h1 = compute_email_hash("alice@example.com")
        h2 = compute_email_hash("alice@example.com")
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex

    def test_is_case_insensitive(self, monkeypatch):
        monkeypatch.setattr("rentivo.settings.settings.secret_key", "test-secret-1")
        from rentivo.blind_index import compute_email_hash

        assert compute_email_hash("Alice@Example.COM") == compute_email_hash("alice@example.com")

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setattr("rentivo.settings.settings.secret_key", "test-secret-1")
        from rentivo.blind_index import compute_email_hash

        assert compute_email_hash("  alice@example.com  ") == compute_email_hash("alice@example.com")

    def test_different_keys_produce_different_hashes(self, monkeypatch):
        from rentivo.blind_index import compute_email_hash

        monkeypatch.setattr("rentivo.settings.settings.secret_key", "secret-A")
        h_a = compute_email_hash("alice@example.com")

        # Reset cache by hand because monkeypatch only resets between tests.
        import rentivo.blind_index

        rentivo.blind_index._cached_key = None
        monkeypatch.setattr("rentivo.settings.settings.secret_key", "secret-B")
        h_b = compute_email_hash("alice@example.com")
        assert h_a != h_b

    def test_different_emails_produce_different_hashes(self, monkeypatch):
        monkeypatch.setattr("rentivo.settings.settings.secret_key", "test-secret-1")
        from rentivo.blind_index import compute_email_hash

        assert compute_email_hash("alice@example.com") != compute_email_hash("bob@example.com")

    def test_empty_email_returns_empty_string(self, monkeypatch):
        """Empty email = no hash — matches the encryption-backend no-op contract."""
        monkeypatch.setattr("rentivo.settings.settings.secret_key", "test-secret-1")
        from rentivo.blind_index import compute_email_hash

        assert compute_email_hash("") == ""

    def test_whitespace_only_email_returns_empty_string(self, monkeypatch):
        monkeypatch.setattr("rentivo.settings.settings.secret_key", "test-secret-1")
        from rentivo.blind_index import compute_email_hash

        assert compute_email_hash("   ") == ""
        assert compute_email_hash("\t\n") == ""
