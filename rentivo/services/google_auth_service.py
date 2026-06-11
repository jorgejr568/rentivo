from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.parse import urlencode

import httpx
import structlog

logger = structlog.get_logger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


class _AsyncHttpResponse(Protocol):
    def json(self) -> dict: ...
    def raise_for_status(self) -> None: ...


class _AsyncHttpClient(Protocol):
    async def post(self, url: str, *, data: dict[str, str], timeout: float) -> _AsyncHttpResponse: ...
    async def get(self, url: str, *, headers: dict[str, str], timeout: float) -> _AsyncHttpResponse: ...
    async def aclose(self) -> None: ...


HttpClientFactory = Callable[[], _AsyncHttpClient]


def _default_factory() -> _AsyncHttpClient:
    return httpx.AsyncClient(timeout=10.0)


@dataclass(frozen=True)
class GoogleUserInfo:
    sub: str
    email: str
    email_verified: bool


class GoogleAuthService:
    """OAuth 2.0 authorization-code flow against Google.

    Uses the OIDC userinfo endpoint instead of parsing ID tokens — both the
    token exchange and the userinfo fetch are direct server-to-Google TLS
    calls, so no local signature verification (and no JWT dependency) is
    needed. Any failure degrades to ``None``; callers show a generic error.
    """

    def __init__(
        self,
        enabled: bool,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        auth_url: str = GOOGLE_AUTH_URL,
        token_url: str = GOOGLE_TOKEN_URL,
        userinfo_url: str = GOOGLE_USERINFO_URL,
        http_client_factory: HttpClientFactory = _default_factory,
    ) -> None:
        self.enabled = enabled
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_url = auth_url
        self.token_url = token_url
        self.userinfo_url = userinfo_url
        self._factory = http_client_factory

    @property
    def is_enabled(self) -> bool:
        return bool(self.enabled and self.client_id and self.client_secret)

    def build_authorization_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email",
            "state": state,
            "prompt": "select_account",
        }
        return f"{self.auth_url}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> GoogleUserInfo | None:
        if not self.is_enabled:
            return None

        client = self._factory()
        try:
            try:
                token_response = await client.post(
                    self.token_url,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "code": code,
                        "grant_type": "authorization_code",
                        "redirect_uri": self.redirect_uri,
                    },
                    timeout=10.0,
                )
                token_response.raise_for_status()
                access_token = str(token_response.json().get("access_token", ""))
                if not access_token:
                    logger.warning("google_auth_no_access_token")
                    return None
                userinfo_response = await client.get(
                    self.userinfo_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10.0,
                )
                userinfo_response.raise_for_status()
                payload = userinfo_response.json()
            except Exception as exc:
                logger.warning("google_auth_exchange_failed", error=str(exc))
                return None
        finally:
            await client.aclose()

        sub = str(payload.get("sub", ""))
        email = str(payload.get("email", "")).strip().lower()
        if not sub or not email:
            logger.warning("google_auth_userinfo_incomplete", has_sub=bool(sub), has_email=bool(email))
            return None
        return GoogleUserInfo(sub=sub, email=email, email_verified=bool(payload.get("email_verified")))
