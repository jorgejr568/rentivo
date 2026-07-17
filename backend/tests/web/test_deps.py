"""Tests for web middleware and deps edge cases."""

import asyncio
from unittest.mock import patch

from legacy_web.deps import AuthMiddleware, DBConnectionMiddleware


class TestAuthMiddlewareNonHTTP:
    def test_non_http_scope_passes_through(self):
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = AuthMiddleware(inner_app)
        scope = {"type": "websocket"}

        asyncio.run(middleware(scope, None, None))
        assert called


class TestDBConnectionMiddlewareNonHTTP:
    def test_non_http_scope_passes_through(self):
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = DBConnectionMiddleware(inner_app)
        scope = {"type": "websocket"}

        asyncio.run(middleware(scope, None, None))
        assert called


class TestRenderInviteCountException:
    def test_invite_count_exception_falls_back_to_zero(self, auth_client, test_engine):
        """When counting pending invites raises an exception, fall back to 0."""
        with patch(
            "legacy_web.deps.SQLAlchemyInviteRepository.count_pending_for_user",
            side_effect=Exception("DB error"),
        ):
            response = auth_client.get("/billings/")
        assert response.status_code == 200


class TestLegacySessionEmailHydration:
    """Pre-migration sessions had `username` but no `email`; render() backfills email
    from the DB so the navbar keeps rendering for existing users without a forced logout."""

    def test_hydrates_email_for_legacy_session(self, test_engine):
        from legacy_web.deps import _hydrate_legacy_session_email
        from rentivo.encryption.base64 import Base64Backend
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository
        from rentivo.services.user_service import UserService

        with test_engine.connect() as conn:
            user = UserService(SQLAlchemyUserRepository(conn, Base64Backend())).create_user(
                "legacy@example.com", "secret"
            )

        session = {"user_id": user.id, "username": "legacy@example.com"}
        request = _fake_request(session, db_conn=test_engine.connect())
        try:
            email = _hydrate_legacy_session_email(request, user.id)
        finally:
            request.state.db_conn.close()

        assert email == "legacy@example.com"
        assert session["email"] == "legacy@example.com"
        assert "username" not in session

    def test_returns_existing_email_without_db_lookup(self):
        from legacy_web.deps import _hydrate_legacy_session_email

        session = {"user_id": 7, "email": "current@example.com"}
        request = _fake_request(session)
        # No connection needed — this path must not touch the DB.
        assert _hydrate_legacy_session_email(request, 7) == "current@example.com"

    def test_returns_none_for_anonymous(self):
        from legacy_web.deps import _hydrate_legacy_session_email

        session: dict = {}
        request = _fake_request(session)
        assert _hydrate_legacy_session_email(request, None) is None

    def test_handles_missing_user_record(self, test_engine):
        from legacy_web.deps import _hydrate_legacy_session_email

        session = {"user_id": 9999, "username": "ghost@example.com"}
        request = _fake_request(session, db_conn=test_engine.connect())
        try:
            email = _hydrate_legacy_session_email(request, 9999)
        finally:
            request.state.db_conn.close()
        assert email is None
        assert "username" not in session


# NOTE: TestTurnstileServiceFactory and TestJobServiceFactory were removed
# in the RequestServices migration — the per-factory functions they tested
# (get_turnstile_service / get_job_service) no longer exist. Equivalent
# coverage now lives in tests/web/test_services_container.py against the
# lazy properties of RequestServices.


def _fake_request(session: dict, db_conn=None):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "headers": [],
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "session": session,
    }
    request = Request(scope)
    request.state.db_conn = db_conn
    return request
