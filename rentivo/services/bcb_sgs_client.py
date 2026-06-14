from __future__ import annotations

from functools import reduce
from typing import Awaitable, Callable, Protocol

import httpx
import structlog

from rentivo.observability import traced

logger = structlog.get_logger(__name__)

# SGS monthly series codes (single source of truth).
IGPM_SERIES = 189
IPCA_SERIES = 433


def accumulated_factor(values: list[float]) -> float:
    """Compound a list of monthly percentage variations into an accumulated %.

    ``accumulated_pct = (prod(1 + v_i / 100) - 1) * 100``. An empty list is 0.0.
    Pure and unit-testable — no I/O.
    """
    product = reduce(lambda acc, v: acc * (1 + v / 100), values, 1.0)
    return (product - 1) * 100


class _AsyncHttpResponse(Protocol):
    def json(self) -> object: ...
    def raise_for_status(self) -> None: ...


class _AsyncHttpClient(Protocol):
    async def get(self, url: str, *, timeout: float) -> _AsyncHttpResponse: ...
    async def aclose(self) -> None: ...


HttpClientFactory = Callable[[], _AsyncHttpClient]


def _default_factory() -> _AsyncHttpClient:
    return httpx.AsyncClient(timeout=10.0)


class BcbSgsClient:
    """Fetches the last 12 monthly values of a Banco Central SGS series and
    returns the accumulated 12-month percentage, or ``None`` on any failure."""

    def __init__(
        self,
        base_url: str,
        http_client_factory: HttpClientFactory = _default_factory,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._factory = http_client_factory

    def _url(self, series_code: int) -> str:
        return f"{self.base_url}/dados/serie/bcdata.sgs.{series_code}/dados/ultimos/12?formato=json"

    @traced("bcb_sgs.fetch_accumulated")
    async def fetch_accumulated(self, series_code: int) -> float | None:
        client = self._factory()
        try:
            try:
                response = await client.get(self._url(series_code), timeout=10.0)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    logger.warning("bcb_sgs_unexpected_payload", series=series_code)
                    return None
                values = [float(entry["valor"]) for entry in payload]
            except Exception as exc:
                logger.warning("bcb_sgs_fetch_failed", series=series_code, error=str(exc))
                return None
        finally:
            close = getattr(client, "aclose", None)
            if close is not None:
                maybe = close()
                if isinstance(maybe, Awaitable):
                    await maybe
        return accumulated_factor(values)
