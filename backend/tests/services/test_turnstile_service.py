from unittest.mock import AsyncMock

import pytest

from rentivo.services.turnstile_service import TurnstileService


def _make_response(success: bool, error_codes: list[str] | None = None):
    response = AsyncMock()
    response.json = lambda: {"success": success, "error-codes": error_codes or []}
    response.raise_for_status = lambda: None
    return response


@pytest.mark.asyncio
async def test_disabled_when_no_keys():
    service = TurnstileService(site_key="", secret_key="", verify_url="x")
    assert service.is_enabled is False
    # verify() short-circuits to True so callers can use the same code path.
    assert await service.verify(token="anything", remote_ip="1.2.3.4") is True


@pytest.mark.asyncio
async def test_enabled_when_both_keys_set():
    service = TurnstileService(site_key="sk", secret_key="ss", verify_url="x")
    assert service.is_enabled is True


@pytest.mark.asyncio
async def test_verify_success_calls_cloudflare_with_expected_payload():
    client = AsyncMock()
    client.post = AsyncMock(return_value=_make_response(success=True))
    service = TurnstileService(
        site_key="sk",
        secret_key="cf-secret",
        verify_url="https://example.invalid/siteverify",
        http_client_factory=lambda: client,
    )
    ok = await service.verify(token="cf-token", remote_ip="9.9.9.9")
    assert ok is True
    client.post.assert_awaited_once()
    args, kwargs = client.post.call_args
    assert args[0] == "https://example.invalid/siteverify"
    assert kwargs["data"] == {
        "secret": "cf-secret",
        "response": "cf-token",
        "remoteip": "9.9.9.9",
    }


@pytest.mark.asyncio
async def test_verify_failure_returns_false():
    client = AsyncMock()
    client.post = AsyncMock(return_value=_make_response(success=False, error_codes=["timeout-or-duplicate"]))
    service = TurnstileService(
        site_key="sk",
        secret_key="ss",
        verify_url="x",
        http_client_factory=lambda: client,
    )
    assert await service.verify(token="t", remote_ip="1.1.1.1") is False


@pytest.mark.asyncio
async def test_verify_empty_token_short_circuits_when_enabled():
    """An empty token from the form is invalid — never call Cloudflare."""
    client = AsyncMock()
    client.post = AsyncMock()
    service = TurnstileService(
        site_key="sk",
        secret_key="ss",
        verify_url="x",
        http_client_factory=lambda: client,
    )
    assert await service.verify(token="", remote_ip="1.1.1.1") is False
    client.post.assert_not_called()


def test_default_factory_returns_async_httpx_client():
    """The default factory builds a real httpx.AsyncClient so callers don't need to wire one up."""
    import httpx

    from rentivo.services.turnstile_service import _default_factory

    client = _default_factory()
    try:
        assert isinstance(client, httpx.AsyncClient)
    finally:
        # AsyncClient.close() is sync-safe enough at construction time; ignore.
        pass


@pytest.mark.asyncio
async def test_verify_swallows_http_errors_as_false():
    client = AsyncMock()
    client.post = AsyncMock(side_effect=RuntimeError("network down"))
    service = TurnstileService(
        site_key="sk",
        secret_key="ss",
        verify_url="x",
        http_client_factory=lambda: client,
    )
    assert await service.verify(token="t", remote_ip="1.1.1.1") is False
