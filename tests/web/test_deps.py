"""Tests for web middleware and deps edge cases."""

import asyncio
from unittest.mock import MagicMock, patch

from starlette.requests import Request

import web.deps as deps_module
from web.deps import (
    AuthMiddleware,
    DBConnectionMiddleware,
    get_bill_service,
    get_theme_service,
    get_user_service,
)
from web.request_scope import (
    close_request_scope,
    count_pending_invites_for_user,
    get_request_scope,
    get_request_services,
)


class TestAuthMiddlewareNonHTTP:
    def test_non_http_scope_passes_through(self):
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = AuthMiddleware(inner_app)
        scope = {"type": "websocket"}

        asyncio.get_event_loop().run_until_complete(middleware(scope, None, None))
        assert called


class TestDBConnectionMiddlewareNonHTTP:
    def test_non_http_scope_passes_through(self):
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = DBConnectionMiddleware(inner_app)
        scope = {"type": "websocket"}

        asyncio.get_event_loop().run_until_complete(middleware(scope, None, None))
        assert called


class TestRenderInviteCountException:
    def test_invite_count_exception_falls_back_to_zero(self, auth_client, test_engine):
        """When counting pending invites raises an exception, fall back to 0."""
        with patch(
            "web.deps.count_pending_invites_for_user",
            side_effect=Exception("DB error"),
        ):
            response = auth_client.get("/billings/")
        assert response.status_code == 200


class TestRequestScopedServices:
    def test_request_reuses_cached_services(self):
        request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "state": {}})

        with patch("web.deps.get_storage", return_value=MagicMock()) as mock_get_storage:
            user_service = get_user_service(request)
            assert get_user_service(request) is user_service

            bill_service = get_bill_service(request)
            theme_service = get_theme_service(request)

        services = get_request_services(
            request,
            engine_factory=deps_module.get_engine,
            storage_factory=deps_module.get_storage,
        )

        assert services.user_service is user_service
        assert get_bill_service(request) is bill_service
        assert bill_service.theme_service is theme_service
        mock_get_storage.assert_called_once_with()


class TestRequestScope:
    def test_get_request_scope_reuses_scope(self):
        request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "state": {}})
        engine = MagicMock()
        storage_factory = MagicMock(return_value=MagicMock())

        scope = get_request_scope(request, engine_factory=lambda: engine, storage_factory=storage_factory)

        assert get_request_scope(request, engine_factory=lambda: engine, storage_factory=storage_factory) is scope

    def test_scope_lazily_opens_connection_and_closes_it(self):
        request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "state": {}})
        conn = MagicMock()
        engine = MagicMock()
        engine.connect.return_value = conn

        scope = get_request_scope(request, engine_factory=lambda: engine, storage_factory=lambda: MagicMock())

        assert scope.conn is conn
        assert scope.conn is conn
        engine.connect.assert_called_once_with()

        close_request_scope(request)
        conn.close.assert_called_once_with()
        assert not hasattr(request.state, "_request_scope")
        assert scope._services is None

    def test_count_pending_invites_uses_cached_services(self):
        request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "state": {}})
        invite_repo = MagicMock()
        invite_repo.count_pending_for_user.return_value = 4

        scope = get_request_scope(
            request,
            engine_factory=MagicMock(),
            storage_factory=lambda: MagicMock(),
        )
        scope._services = MagicMock(invite_repo=invite_repo)

        result = count_pending_invites_for_user(
            request,
            7,
            engine_factory=MagicMock(),
            storage_factory=lambda: MagicMock(),
        )

        assert result == 4
        invite_repo.count_pending_for_user.assert_called_once_with(7)
