"""Tests for web middleware and deps edge cases."""
import asyncio
from unittest.mock import MagicMock, patch

from web.deps import AuthMiddleware, DBConnectionMiddleware


class TestAuthMiddlewareNonHTTP:
    def test_non_http_scope_passes_through(self):
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = AuthMiddleware(inner_app)
        scope = {"type": "websocket"}

        asyncio.get_event_loop().run_until_complete(
            middleware(scope, None, None)
        )
        assert called


class TestDBConnectionMiddlewareNonHTTP:
    def test_non_http_scope_passes_through(self):
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = DBConnectionMiddleware(inner_app)
        scope = {"type": "websocket"}

        asyncio.get_event_loop().run_until_complete(
            middleware(scope, None, None)
        )
        assert called


class TestRenderInviteCountException:
    def test_invite_count_exception_falls_back_to_zero(self, auth_client, test_engine):
        """When counting pending invites raises an exception, fall back to 0."""
        with patch(
            "web.deps.SQLAlchemyInviteRepository.count_pending_for_user",
            side_effect=Exception("DB error"),
        ):
            response = auth_client.get("/billings/")
        assert response.status_code == 200
