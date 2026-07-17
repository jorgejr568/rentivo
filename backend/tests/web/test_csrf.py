"""Tests for CSRF middleware edge cases."""

import asyncio
import re

from legacy_web.csrf import CSRFMiddleware


class TestCSRFMismatch:
    def test_wrong_csrf_token_redirects(self, auth_client):
        """POST with wrong CSRF token should redirect back."""
        response = auth_client.post(
            "/change-password",
            data={
                "csrf_token": "wrong-token-value",
                "current_password": "testpass",
                "new_password": "new",
                "confirm_password": "new",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_missing_csrf_token_redirects(self, auth_client):
        """POST without csrf_token field should redirect back."""
        response = auth_client.post(
            "/change-password",
            data={
                "current_password": "testpass",
                "new_password": "new",
                "confirm_password": "new",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_json_post_without_token_is_rejected(self, auth_client):
        """JSON POST with no CSRF token (neither field nor header) is rejected."""
        response = auth_client.post(
            "/logout",
            headers={"content-type": "application/json"},
            content="{}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert auth_client.cookies.get("session") is not None  # didn't reach logout


class TestCSRFHeaderToken:
    def test_json_post_with_valid_header_token_passes(self, auth_client):
        """JSON POST with a valid X-CSRF-Token header must be accepted."""
        page = auth_client.get("/change-password")
        m = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        assert m, "csrf_token not found in change-password page"
        csrf = m.group(1)

        response = auth_client.post(
            "/logout",
            headers={
                "content-type": "application/json",
                "X-CSRF-Token": csrf,
            },
            content="{}",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_json_post_with_wrong_header_token_is_rejected(self, auth_client):
        response = auth_client.post(
            "/logout",
            headers={
                "content-type": "application/json",
                "X-CSRF-Token": "not-the-real-token",
            },
            content="{}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert auth_client.cookies.get("session") is not None


class TestCSRFNonHTTPScope:
    def test_non_http_scope_passes_through(self):
        """Non-HTTP scopes (like websocket) should pass through CSRF."""
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = CSRFMiddleware(inner_app)
        scope = {"type": "websocket"}

        asyncio.run(middleware(scope, None, None))
        assert called
