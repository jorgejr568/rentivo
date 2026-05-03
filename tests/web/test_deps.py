"""Tests for web middleware and deps edge cases."""

import asyncio
from unittest.mock import patch

from web.deps import AuthMiddleware, DBConnectionMiddleware


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
            "web.deps.SQLAlchemyInviteRepository.count_pending_for_user",
            side_effect=Exception("DB error"),
        ):
            response = auth_client.get("/billings/")
        assert response.status_code == 200


class TestLegacySessionEmailHydration:
    """Pre-migration sessions had `username` but no `email`; render() backfills email
    from the DB so the navbar keeps rendering for existing users without a forced logout."""

    def test_hydrates_email_for_legacy_session(self, test_engine):
        from rentivo.encryption.base64 import Base64Backend
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository
        from rentivo.services.user_service import UserService
        from web.deps import _hydrate_legacy_session_email

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
        from web.deps import _hydrate_legacy_session_email

        session = {"user_id": 7, "email": "current@example.com"}
        request = _fake_request(session)
        # No connection needed — this path must not touch the DB.
        assert _hydrate_legacy_session_email(request, 7) == "current@example.com"

    def test_returns_none_for_anonymous(self):
        from web.deps import _hydrate_legacy_session_email

        session: dict = {}
        request = _fake_request(session)
        assert _hydrate_legacy_session_email(request, None) is None

    def test_handles_missing_user_record(self, test_engine):
        from web.deps import _hydrate_legacy_session_email

        session = {"user_id": 9999, "username": "ghost@example.com"}
        request = _fake_request(session, db_conn=test_engine.connect())
        try:
            email = _hydrate_legacy_session_email(request, 9999)
        finally:
            request.state.db_conn.close()
        assert email is None
        assert "username" not in session


class TestTurnstileServiceFactory:
    def test_get_turnstile_service_uses_settings(self, monkeypatch):
        from rentivo.settings import settings
        from web.deps import get_turnstile_service

        monkeypatch.setattr(settings, "turnstile_site_key", "factory-site")
        monkeypatch.setattr(settings, "turnstile_secret_key", "factory-secret")
        monkeypatch.setattr(settings, "turnstile_verify_url", "https://verify.invalid/x")

        # Build a fake Request just to satisfy the signature.
        class _Req:
            pass

        service = get_turnstile_service(_Req())
        assert service.site_key == "factory-site"
        assert service.secret_key == "factory-secret"
        assert service.verify_url == "https://verify.invalid/x"


class TestJobServiceFactory:
    """Coverage for the factory until web routes call it (Tasks 11-15)."""

    def test_get_job_service_returns_job_service(self, test_engine):
        from rentivo.services.job_service import JobService
        from web.deps import get_job_service

        request = _fake_request({}, db_conn=test_engine.connect())
        try:
            service = get_job_service(request)
        finally:
            request.state.db_conn.close()

        assert isinstance(service, JobService)


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
