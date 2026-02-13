"""Tests for CSRF middleware edge cases."""
import asyncio

from web.csrf import CSRFMiddleware


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

    def test_json_post_passes_through(self, auth_client):
        """POST with JSON content type (not form) should pass through CSRF."""
        response = auth_client.post(
            "/logout",
            headers={"content-type": "application/json"},
            content="{}",
            follow_redirects=False,
        )
        # Logout clears session and redirects even without CSRF for non-form content
        assert response.status_code == 302


class TestCSRFNonHTTPScope:
    def test_non_http_scope_passes_through(self):
        """Non-HTTP scopes (like websocket) should pass through CSRF."""
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = CSRFMiddleware(inner_app)
        scope = {"type": "websocket"}

        asyncio.get_event_loop().run_until_complete(
            middleware(scope, None, None)
        )
        assert called
