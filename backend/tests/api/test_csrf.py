from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from starlette.responses import Response

from rentivo.api.app import create_app
from rentivo.api.authentication import ACCESS_COOKIE_NAME
from rentivo.api.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, issue_csrf_token, require_csrf
from rentivo.api.dependencies import get_services
from rentivo.api.principal import Principal
from rentivo.models.api_key import APIKey
from rentivo.models.user import User

LOGIN_SECRET = f"rntv-v1-{'L' * 43}"
SECOND_LOGIN_SECRET = f"rntv-v1-{'S' * 43}"
INTEGRATION_SECRET = f"rntv-v1-{'I' * 43}"


def _key(*, key_id: int, uuid: str, is_login_token: bool) -> APIKey:
    return APIKey(
        id=key_id,
        uuid=uuid,
        user_id=7,
        name="Browser" if is_login_token else "Integration",
        secret_hash=bytes([key_id]) * 32,
        key_start="abcd",
        key_end="yz",
        is_login_token=is_login_token,
        scopes=frozenset({"profile:read"}),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class FakeAPIKeyService:
    def __init__(self, keys: dict[str, APIKey]) -> None:
        self.keys = keys

    def authenticate(self, secret: str) -> APIKey | None:
        return self.keys.get(secret)


class FakeUserService:
    def get_by_id(self, user_id: int) -> User | None:
        if user_id != 7:
            return None
        return User(id=7, email="person@example.com")


@pytest.fixture()
def principals() -> dict[str, Principal]:
    user = User(id=7, email="person@example.com")
    login_key = _key(key_id=1, uuid="login-key-uuid", is_login_token=True)
    second_login_key = _key(key_id=2, uuid="second-login-key-uuid", is_login_token=True)
    integration_key = _key(key_id=3, uuid="integration-key-uuid", is_login_token=False)
    return {
        "login": Principal(user=user, api_key=login_key, source="web"),
        "second_login": Principal(user=user, api_key=second_login_key, source="web"),
        "integration": Principal(user=user, api_key=integration_key, source="integration"),
    }


@pytest.fixture()
def csrf_client(principals: dict[str, Principal], monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import rentivo.api.csrf as csrf

    monkeypatch.setattr(csrf.settings, "secret_key", "csrf-test-signing-key")
    services = SimpleNamespace(
        api_key=FakeAPIKeyService(
            {
                LOGIN_SECRET: principals["login"].api_key,
                SECOND_LOGIN_SECRET: principals["second_login"].api_key,
                INTEGRATION_SECRET: principals["integration"].api_key,
            }
        ),
        mfa=SimpleNamespace(user_requires_mfa_setup=lambda _user_id: False),
        user=FakeUserService(),
    )
    app = create_app()
    app.dependency_overrides[get_services] = lambda: services

    @app.api_route(
        "/api/v1/test/csrf",
        methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
    )
    async def csrf_endpoint(_csrf: None = Depends(require_csrf)) -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def _cookies(access_secret: str, csrf_token: str | None = None) -> str:
    values = [f"{ACCESS_COOKIE_NAME}={access_secret}"]
    if csrf_token is not None:
        values.append(f"{CSRF_COOKIE_NAME}={csrf_token}")
    return "; ".join(values)


def _cookie_mutation(
    client: TestClient,
    *,
    access_secret: str = LOGIN_SECRET,
    cookie_token: str | None = None,
    header_token: str | None = None,
    authorization: str | None = None,
) -> Any:
    headers = {"Cookie": _cookies(access_secret, cookie_token)}
    if header_token is not None:
        headers[CSRF_HEADER_NAME] = header_token
    if authorization is not None:
        headers["Authorization"] = authorization
    return client.post("/api/v1/test/csrf", headers=headers)


def test_csrf_issuance_returns_bootstrap_token_and_non_http_only_cookie(
    principals: dict[str, Principal],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rentivo.api.csrf as csrf

    monkeypatch.setattr(csrf.settings, "secret_key", "csrf-test-signing-key")
    response = Response()

    bootstrap_token = issue_csrf_token(response, principals["login"])

    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{CSRF_COOKIE_NAME}={bootstrap_token};")
    assert "HttpOnly" not in cookie
    assert "Path=/" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" in cookie


def test_csrf_issuance_honors_plain_http_development_cookie_settings(
    principals: dict[str, Principal],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rentivo.api.csrf as csrf

    monkeypatch.setattr(csrf.settings, "secret_key", "csrf-test-signing-key")
    monkeypatch.setattr(csrf.settings, "csrf_cookie_name", "rentivo_csrf")
    monkeypatch.setattr(csrf.settings, "cookie_secure", False)
    response = Response()

    token = issue_csrf_token(response, principals["login"])

    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"rentivo_csrf={token};")
    assert "Secure" not in cookie


def test_cookie_authenticated_mutation_requires_exact_valid_double_submit(
    csrf_client: TestClient,
    principals: dict[str, Principal],
) -> None:
    token = issue_csrf_token(Response(), principals["login"])

    response = _cookie_mutation(csrf_client, cookie_token=token, header_token=token)

    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.parametrize(
    ("cookie_variant", "header_variant"),
    [
        (None, "valid"),
        ("valid", None),
        ("valid", "different"),
        ("different", "valid"),
    ],
)
def test_cookie_authenticated_mutation_rejects_missing_or_non_exact_double_submit(
    csrf_client: TestClient,
    principals: dict[str, Principal],
    cookie_variant: str | None,
    header_variant: str | None,
) -> None:
    token = issue_csrf_token(Response(), principals["login"])
    values = {
        "valid": token,
        "different": f"{token}x",
    }

    response = _cookie_mutation(
        csrf_client,
        cookie_token=None if cookie_variant is None else values[cookie_variant],
        header_token=None if header_variant is None else values[header_variant],
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_matching_tampered_csrf_values_are_rejected_by_hmac_validation(
    csrf_client: TestClient,
    principals: dict[str, Principal],
) -> None:
    token = issue_csrf_token(Response(), principals["login"])
    tampered = f"{token[:-1]}{'A' if token[-1] != 'A' else 'B'}"

    response = _cookie_mutation(csrf_client, cookie_token=tampered, header_token=tampered)

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


@pytest.mark.parametrize("malformed", ["missing-separator", ".signature", "nonce."])
def test_matching_malformed_csrf_values_are_rejected(
    csrf_client: TestClient,
    malformed: str,
) -> None:
    response = _cookie_mutation(
        csrf_client,
        cookie_token=malformed,
        header_token=malformed,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_non_ascii_csrf_value_returns_stable_forbidden_problem(csrf_client: TestClient) -> None:
    response = csrf_client.post(
        "/api/v1/test/csrf",
        headers={
            b"Cookie": _cookies(LOGIN_SECRET, "nonce.é").encode(),
            CSRF_HEADER_NAME.encode(): "nonce.é".encode(),
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_csrf_hmac_is_bound_to_the_authenticated_api_key_uuid(
    csrf_client: TestClient,
    principals: dict[str, Principal],
) -> None:
    first_key_token = issue_csrf_token(Response(), principals["login"])

    response = _cookie_mutation(
        csrf_client,
        access_secret=SECOND_LOGIN_SECRET,
        cookie_token=first_key_token,
        header_token=first_key_token,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_cookie_authenticated_methods_do_not_require_csrf(
    csrf_client: TestClient,
    method: str,
) -> None:
    response = csrf_client.request(
        method,
        "/api/v1/test/csrf",
        headers={"Cookie": _cookies(LOGIN_SECRET)},
    )

    assert response.status_code == 200


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_bearer_only_mutations_bypass_csrf(csrf_client: TestClient, method: str) -> None:
    response = csrf_client.request(
        method,
        "/api/v1/test/csrf",
        headers={"Authorization": f"Bearer {INTEGRATION_SECRET}"},
    )

    assert response.status_code == 200


def test_matching_cookie_and_bearer_is_not_bearer_only(csrf_client: TestClient) -> None:
    response = _cookie_mutation(
        csrf_client,
        authorization=f"Bearer {LOGIN_SECRET}",
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
