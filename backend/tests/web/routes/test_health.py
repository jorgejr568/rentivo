"""Tests for the /health liveness probe."""

from __future__ import annotations


class TestHealthEndpoint:
    def test_returns_200_ok_json(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_does_not_require_auth(self, client):
        """Probes run unauthenticated — no redirect to /login."""
        r = client.get("/health", follow_redirects=False)
        assert r.status_code == 200
