from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest

from rentivo.services.google_auth_service import GoogleAuthService, GoogleUserInfo


def _make_service(client=None, **overrides):
    kwargs = dict(
        enabled=True,
        client_id="test-client-id",
        client_secret="test-client-secret",
        redirect_uri="http://localhost:8000/auth/google/callback",
    )
    kwargs.update(overrides)
    if client is not None:
        kwargs["http_client_factory"] = lambda: client
    return GoogleAuthService(**kwargs)


def _json_response(payload: dict):
    response = AsyncMock()
    response.json = lambda: payload
    response.raise_for_status = lambda: None
    return response


def _make_client(token_payload: dict, userinfo_payload: dict):
    client = AsyncMock()
    client.post = AsyncMock(return_value=_json_response(token_payload))
    client.get = AsyncMock(return_value=_json_response(userinfo_payload))
    return client


class TestIsEnabled:
    def test_disabled_when_flag_off(self):
        assert _make_service(enabled=False).is_enabled is False

    def test_disabled_when_client_id_missing(self):
        assert _make_service(client_id="").is_enabled is False

    def test_disabled_when_secret_missing(self):
        assert _make_service(client_secret="").is_enabled is False

    def test_enabled_when_all_set(self):
        assert _make_service().is_enabled is True


class TestBuildAuthorizationUrl:
    def test_url_contains_expected_params(self):
        service = _make_service()
        url = service.build_authorization_url("state-123")
        parsed = urlparse(url)
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        params = parse_qs(parsed.query)
        assert params["client_id"] == ["test-client-id"]
        assert params["redirect_uri"] == ["http://localhost:8000/auth/google/callback"]
        assert params["response_type"] == ["code"]
        assert params["scope"] == ["openid email"]
        assert params["state"] == ["state-123"]


class TestExchangeCode:
    @pytest.mark.asyncio
    async def test_returns_none_when_disabled(self):
        service = _make_service(enabled=False)
        assert await service.exchange_code("code") is None

    @pytest.mark.asyncio
    async def test_success_returns_userinfo(self):
        client = _make_client(
            {"access_token": "at-1"},
            {"sub": "g-sub-1", "email": "User@Example.COM", "email_verified": True},
        )
        service = _make_service(client=client)
        info = await service.exchange_code("auth-code-1")
        assert info == GoogleUserInfo(sub="g-sub-1", email="user@example.com", email_verified=True)
        # token exchange payload
        args, kwargs = client.post.call_args
        assert args[0] == "https://oauth2.googleapis.com/token"
        assert kwargs["data"] == {
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "code": "auth-code-1",
            "grant_type": "authorization_code",
            "redirect_uri": "http://localhost:8000/auth/google/callback",
        }
        # userinfo call carries the bearer token
        args, kwargs = client.get.call_args
        assert args[0] == "https://openidconnect.googleapis.com/v1/userinfo"
        assert kwargs["headers"] == {"Authorization": "Bearer at-1"}
        client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unverified_email_passes_through(self):
        client = _make_client(
            {"access_token": "at-1"},
            {"sub": "g-sub-1", "email": "u@e.com", "email_verified": False},
        )
        info = await _make_service(client=client).exchange_code("c")
        assert info.email_verified is False

    @pytest.mark.asyncio
    async def test_returns_none_when_access_token_missing(self):
        client = _make_client({"error": "invalid_grant"}, {})
        assert await _make_service(client=client).exchange_code("c") is None
        client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_token_http_error(self):
        client = AsyncMock()
        client.post = AsyncMock(side_effect=RuntimeError("boom"))
        assert await _make_service(client=client).exchange_code("c") is None
        client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_userinfo_http_error(self):
        client = AsyncMock()
        client.post = AsyncMock(return_value=_json_response({"access_token": "at"}))
        client.get = AsyncMock(side_effect=RuntimeError("boom"))
        assert await _make_service(client=client).exchange_code("c") is None

    @pytest.mark.asyncio
    async def test_returns_none_when_sub_missing(self):
        client = _make_client({"access_token": "at"}, {"email": "u@e.com", "email_verified": True})
        assert await _make_service(client=client).exchange_code("c") is None

    @pytest.mark.asyncio
    async def test_returns_none_when_email_missing(self):
        client = _make_client({"access_token": "at"}, {"sub": "g-1", "email_verified": True})
        assert await _make_service(client=client).exchange_code("c") is None
