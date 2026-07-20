from __future__ import annotations

from typing import Awaitable, Callable, Protocol

import httpx
import structlog

from rentivo.observability import traced

logger = structlog.get_logger(__name__)


class _AsyncHttpResponse(Protocol):
    def json(self) -> dict: ...
    def raise_for_status(self) -> None: ...


class _AsyncHttpClient(Protocol):
    async def post(self, url: str, *, data: dict[str, str], timeout: float) -> _AsyncHttpResponse: ...
    async def aclose(self) -> None: ...


HttpClientFactory = Callable[[], _AsyncHttpClient]


def _default_factory() -> _AsyncHttpClient:
    return httpx.AsyncClient(timeout=5.0)


class TurnstileService:
    """Wraps the Cloudflare Turnstile siteverify endpoint.

    When the keys are empty the service is a no-op: ``is_enabled`` is False and
    ``verify`` short-circuits to True so callers can use a single code path.
    """

    def __init__(
        self,
        site_key: str,
        secret_key: str,
        verify_url: str,
        http_client_factory: HttpClientFactory = _default_factory,
    ) -> None:
        self.site_key = site_key
        self.secret_key = secret_key
        self.verify_url = verify_url
        self._factory = http_client_factory

    @property
    def is_enabled(self) -> bool:
        return bool(self.site_key and self.secret_key)

    @traced("turnstile.verify")
    async def verify(self, token: str, remote_ip: str) -> bool:
        if not self.is_enabled:
            return True
        if not token:
            logger.warning("turnstile_token_missing")
            return False

        client = self._factory()
        try:
            try:
                response = await client.post(
                    self.verify_url,
                    data={"secret": self.secret_key, "response": token, "remoteip": remote_ip},
                    timeout=5.0,
                )
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                logger.warning("turnstile_verify_failed", error=str(exc))
                return False
        finally:
            close = getattr(client, "aclose", None)
            if close is not None:
                maybe = close()
                if isinstance(maybe, Awaitable):
                    await maybe

        ok = bool(payload.get("success"))
        if not ok:
            logger.info("turnstile_rejected", error_codes=payload.get("error-codes"))
        return ok
