from unittest.mock import AsyncMock

import pytest

from rentivo.services.bcb_sgs_client import IGPM_SERIES, IPCA_SERIES, BcbSgsClient, accumulated_factor


def test_series_codes():
    assert IGPM_SERIES == 189
    assert IPCA_SERIES == 433


def test_accumulated_factor_single_value():
    # one month of 1.00% -> 1.00% accumulated
    assert accumulated_factor([1.0]) == pytest.approx(1.0)


def test_accumulated_factor_compounds():
    # two months of 1% each -> (1.01 * 1.01 - 1) * 100 = 2.01%
    assert accumulated_factor([1.0, 1.0]) == pytest.approx(2.01)


def test_accumulated_factor_handles_negatives():
    # +2% then -1% -> (1.02 * 0.99 - 1) * 100 = 0.98%
    assert accumulated_factor([2.0, -1.0]) == pytest.approx(0.98)


def test_accumulated_factor_empty_is_zero():
    assert accumulated_factor([]) == 0.0


def _json_response(payload):
    response = AsyncMock()
    response.json = lambda: payload
    response.raise_for_status = lambda: None
    return response


def _client_returning(payload):
    http = AsyncMock()
    http.get = AsyncMock(return_value=_json_response(payload))
    return http


_TWELVE = [{"data": f"01/{m:02d}/2025", "valor": "1.00"} for m in range(1, 13)]


@pytest.mark.asyncio
async def test_fetch_accumulated_success():
    http = _client_returning(_TWELVE)
    client = BcbSgsClient(base_url="http://bcb.test", http_client_factory=lambda: http)
    pct = await client.fetch_accumulated(IGPM_SERIES)
    # twelve months of 1% compounded
    expected = (1.01**12 - 1) * 100
    assert pct == pytest.approx(expected)
    args, kwargs = http.get.call_args
    assert args[0] == "http://bcb.test/dados/serie/bcdata.sgs.189/dados/ultimos/12?formato=json"
    http.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_returns_none_on_http_error():
    http = AsyncMock()
    http.get = AsyncMock(side_effect=RuntimeError("boom"))
    client = BcbSgsClient(base_url="http://bcb.test", http_client_factory=lambda: http)
    assert await client.fetch_accumulated(IPCA_SERIES) is None
    http.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_returns_none_on_malformed_payload():
    http = _client_returning([{"data": "01/01/2025"}])  # missing 'valor'
    client = BcbSgsClient(base_url="http://bcb.test", http_client_factory=lambda: http)
    assert await client.fetch_accumulated(IGPM_SERIES) is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_non_list_payload():
    http = _client_returning({"error": "nope"})
    client = BcbSgsClient(base_url="http://bcb.test", http_client_factory=lambda: http)
    assert await client.fetch_accumulated(IGPM_SERIES) is None


def test_default_factory_builds_async_client():
    import httpx

    from rentivo.services.bcb_sgs_client import _default_factory

    client = _default_factory()
    assert isinstance(client, httpx.AsyncClient)
