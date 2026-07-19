from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient

from rentivo.api.app import create_app
from rentivo.api.authentication import ACCESS_COOKIE_NAME, get_optional_principal, get_principal
from rentivo.api.csrf import CSRF_COOKIE_NAME
from rentivo.api.dependencies import get_services
from rentivo.api.principal import Principal
from rentivo.models.api_key import APIKey
from rentivo.models.user import User

LOGIN_SECRET = f"rntv-v1-{'L' * 43}"
INTEGRATION_SECRET = f"rntv-v1-{'I' * 43}"
UNKNOWN_SECRET = f"rntv-v1-{'U' * 43}"


def _key(*, uuid: str, secret_hash: bytes, is_login_token: bool) -> APIKey:
    return APIKey(
        id=1 if is_login_token else 2,
        uuid=uuid,
        user_id=7,
        name="Browser" if is_login_token else "Integration",
        secret_hash=secret_hash,
        key_start="abcd",
        key_end="yz",
        is_login_token=is_login_token,
        scopes=frozenset({"profile:read"}),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class FakeAPIKeyService:
    def __init__(self, keys: dict[str, APIKey]) -> None:
        self.keys = keys
        self.authenticate_calls: list[str] = []

    def authenticate(self, secret: str) -> APIKey | None:
        self.authenticate_calls.append(secret)
        return self.keys.get(secret)


class FakeUserService:
    def __init__(self, user: User) -> None:
        self.user = user
        self.get_by_id_calls: list[int] = []

    def get_by_id(self, user_id: int) -> User | None:
        self.get_by_id_calls.append(user_id)
        return self.user if user_id == self.user.id else None


class FakeMFAService:
    def __init__(self) -> None:
        self.setup_required = False
        self.user_requires_mfa_setup_calls: list[int] = []

    def user_requires_mfa_setup(self, user_id: int) -> bool:
        self.user_requires_mfa_setup_calls.append(user_id)
        return self.setup_required


@pytest.fixture()
def login_key() -> APIKey:
    return _key(uuid="login-key-uuid", secret_hash=b"l" * 32, is_login_token=True)


@pytest.fixture()
def integration_key() -> APIKey:
    return _key(uuid="integration-key-uuid", secret_hash=b"i" * 32, is_login_token=False)


@pytest.fixture()
def services(login_key: APIKey, integration_key: APIKey) -> Any:
    return SimpleNamespace(
        api_key=FakeAPIKeyService(
            {
                LOGIN_SECRET: login_key,
                INTEGRATION_SECRET: integration_key,
            }
        ),
        mfa=FakeMFAService(),
        user=FakeUserService(User(id=7, email="person@example.com")),
    )


@pytest.fixture()
def api_client(services: Any) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_services] = lambda: services

    @app.get("/api/v1/test/principal")
    async def principal_endpoint(
        request: Request,
        principal: Principal = Depends(get_principal),
    ) -> dict[str, object]:
        actor = request.state.actor
        return {
            "user_id": principal.user.id,
            "api_key_uuid": principal.api_key.uuid,
            "source": principal.source,
            "actor": {
                "user_id": actor.user_id,
                "email": actor.email,
                "source": actor.source,
                "api_key_uuid": actor.api_key_uuid,
                "is_login_token": actor.is_login_token,
            },
        }

    @app.get("/api/v1/test/optional-principal")
    async def optional_principal_endpoint(
        principal: Principal | None = Depends(get_optional_principal),
    ) -> dict[str, int | None]:
        return {"user_id": None if principal is None else principal.user.id}

    @app.post("/api/v1/test/principal")
    async def principal_body_endpoint(
        payload: dict[str, str],
        principal: Principal = Depends(get_principal),
    ) -> dict[str, object]:
        return {"user_id": principal.user.id, "payload": payload}

    @app.post("/api/v1/test/principal-no-body")
    async def principal_no_body_endpoint(
        principal: Principal = Depends(get_principal),
    ) -> dict[str, int | None]:
        return {"user_id": principal.user.id}

    @app.post("/api/v1/test/principal-raw-body")
    async def principal_raw_body_endpoint(
        request: Request,
        principal: Principal = Depends(get_principal),
    ) -> dict[str, object]:
        return {
            "user_id": principal.user.id,
            "body": (await request.body()).decode("latin-1"),
        }

    return TestClient(app)


def _cookie_header(secret: str, *, csrf: str | None = None) -> str:
    values = [f"{ACCESS_COOKIE_NAME}={secret}"]
    if csrf is not None:
        values.append(f"{CSRF_COOKIE_NAME}={csrf}")
    return "; ".join(values)


@pytest.mark.parametrize(
    ("headers", "expected_source"),
    [
        ({"Cookie": _cookie_header(LOGIN_SECRET)}, "web"),
        ({"Authorization": f"Bearer {LOGIN_SECRET}"}, "mobile"),
    ],
)
def test_cookie_and_bearer_resolve_the_same_principal(
    api_client: TestClient,
    headers: dict[str, str],
    expected_source: str,
) -> None:
    response = api_client.get("/api/v1/test/principal", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "user_id": 7,
        "api_key_uuid": "login-key-uuid",
        "source": expected_source,
        "actor": {
            "user_id": 7,
            "email": "person@example.com",
            "source": expected_source,
            "api_key_uuid": "login-key-uuid",
            "is_login_token": True,
        },
    }


def test_bearer_integration_is_attributed_to_the_integration_source(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/test/principal",
        headers={"Authorization": f"Bearer {INTEGRATION_SECRET}"},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "integration"
    assert response.json()["actor"]["source"] == "integration"
    assert response.json()["actor"]["is_login_token"] is False


@pytest.mark.parametrize(
    "headers",
    [
        {"Cookie": _cookie_header(LOGIN_SECRET)},
        {"Authorization": f"Bearer {LOGIN_SECRET}"},
    ],
)
def test_live_organization_mfa_blocks_login_tokens_on_every_protected_request(
    api_client: TestClient,
    services: Any,
    headers: dict[str, str],
) -> None:
    first = api_client.get("/api/v1/test/principal", headers=headers)
    services.mfa.setup_required = True

    blocked = api_client.get("/api/v1/test/principal", headers=headers)

    assert first.status_code == 200
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "mfa_setup_required"
    assert services.mfa.user_requires_mfa_setup_calls == [7, 7]


def test_live_organization_mfa_does_not_change_integration_key_authentication(
    api_client: TestClient,
    services: Any,
) -> None:
    services.mfa.setup_required = True

    response = api_client.get(
        "/api/v1/test/principal",
        headers={"Authorization": f"Bearer {INTEGRATION_SECRET}"},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "integration"
    assert services.mfa.user_requires_mfa_setup_calls == []


def test_optional_principal_allows_missing_credentials(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/test/optional-principal")

    assert response.status_code == 200
    assert response.json() == {"user_id": None}


def test_required_principal_rejects_missing_credentials(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/test/principal")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


@pytest.mark.parametrize(
    "authorization",
    [
        "Basic credentials",
        "Token credentials",
        "Bearer",
        "Bearer one two",
    ],
)
def test_malformed_or_non_bearer_authorization_is_rejected(
    api_client: TestClient,
    authorization: str,
) -> None:
    response = api_client.get(
        "/api/v1/test/principal",
        headers={"Authorization": authorization},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "malformed_credentials"


def test_unknown_bearer_credential_is_unauthorized_without_clearing_cookies(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/test/principal",
        headers={"Authorization": f"Bearer {UNKNOWN_SECRET}"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    assert response.headers.get_list("set-cookie") == []


def test_mismatched_cookie_and_bearer_are_rejected_before_authentication(
    api_client: TestClient,
    services: Any,
) -> None:
    response = api_client.get(
        "/api/v1/test/principal",
        headers={
            "Cookie": _cookie_header(LOGIN_SECRET),
            "Authorization": f"Bearer {INTEGRATION_SECRET}",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "ambiguous_credentials"
    assert services.api_key.authenticate_calls == []


def test_matching_cookie_and_bearer_are_accepted_as_cookie_authenticated(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/test/principal",
        headers={
            "Cookie": _cookie_header(LOGIN_SECRET),
            "Authorization": f"Bearer {LOGIN_SECRET}",
        },
    )

    assert response.status_code == 200
    assert response.json()["source"] == "web"


def test_stale_cookie_unauthorized_response_clears_access_and_csrf_cookies(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/test/principal",
        headers={"Cookie": _cookie_header(UNKNOWN_SECRET, csrf="stale-csrf")},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    set_cookies = response.headers.get_list("set-cookie")
    for cookie_name in (ACCESS_COOKIE_NAME, CSRF_COOKIE_NAME):
        matching = [value for value in set_cookies if value.startswith(f"{cookie_name}=")]
        assert len(matching) == 1
        assert "Max-Age=0" in matching[0]
        assert "Path=/" in matching[0]
        assert "Secure" in matching[0]


@pytest.mark.parametrize(
    ("method", "url", "kwargs"),
    [
        (
            "GET",
            f"/api/v1/test/principal?api_key={UNKNOWN_SECRET}",
            {"headers": {"Authorization": f"Bearer {LOGIN_SECRET}"}},
        ),
        (
            "POST",
            "/api/v1/test/principal",
            {
                "headers": {"Authorization": f"Bearer {LOGIN_SECRET}"},
                "json": {"api_key": UNKNOWN_SECRET},
            },
        ),
    ],
)
def test_credentials_outside_cookie_or_authorization_header_are_rejected(
    api_client: TestClient,
    method: str,
    url: str,
    kwargs: dict[str, Any],
) -> None:
    response = api_client.request(method, url, **kwargs)

    assert response.status_code == 400
    assert response.json()["code"] == "malformed_credentials"


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"data": {"api_key": UNKNOWN_SECRET}},
        {"files": {"api_key": (None, UNKNOWN_SECRET)}},
        {
            "content": f'{{"api_key":"{UNKNOWN_SECRET}"}}',
            "headers": {"Content-Type": "application/merge-patch+json"},
        },
    ],
)
def test_form_and_json_compatible_body_credentials_are_rejected(
    api_client: TestClient,
    request_kwargs: dict[str, Any],
) -> None:
    headers = {"Authorization": f"Bearer {LOGIN_SECRET}", **request_kwargs.pop("headers", {})}

    response = api_client.post(
        "/api/v1/test/principal-no-body",
        headers=headers,
        **request_kwargs,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "malformed_credentials"


def test_benign_form_body_does_not_change_header_authentication(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/test/principal-no-body",
        headers={"Authorization": f"Bearer {LOGIN_SECRET}"},
        data={"label": "safe"},
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": 7}


@pytest.mark.parametrize(
    ("content_type", "body"),
    [
        ("application/x-www-form-urlencoded", b"label=safe"),
        (
            "multipart/form-data; boundary=rentivo-boundary",
            (
                b"--rentivo-boundary\r\n"
                b'Content-Disposition: form-data; name="label"\r\n\r\n'
                b"safe\r\n"
                b"--rentivo-boundary--\r\n"
            ),
        ),
    ],
)
def test_form_credential_inspection_preserves_raw_body_for_handler(
    api_client: TestClient,
    content_type: str,
    body: bytes,
) -> None:
    response = api_client.post(
        "/api/v1/test/principal-raw-body",
        headers={
            "Authorization": f"Bearer {LOGIN_SECRET}",
            "Content-Type": content_type,
        },
        content=body,
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": 7, "body": body.decode("latin-1")}


def test_nested_body_credentials_are_rejected(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/test/principal",
        headers={"Authorization": f"Bearer {LOGIN_SECRET}"},
        json={"wrapper": [{"api_key": UNKNOWN_SECRET}]},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "malformed_credentials"


def test_benign_nested_body_does_not_change_header_authentication(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/test/principal-no-body",
        headers={"Authorization": f"Bearer {LOGIN_SECRET}"},
        json={"wrapper": ["safe"]},
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": 7}


def test_deeply_nested_json_is_inspected_without_recursion_failure(api_client: TestClient) -> None:
    depth = 900
    content = b'{"wrapper":' * depth + b'"safe"' + b"}" * depth

    response = api_client.post(
        "/api/v1/test/principal-no-body",
        headers={
            "Authorization": f"Bearer {LOGIN_SECRET}",
            "Content-Type": "application/json",
        },
        content=content,
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": 7}


@pytest.mark.parametrize("content", [b"", b"{"])
def test_empty_or_malformed_json_does_not_change_header_authentication(
    api_client: TestClient,
    content: bytes,
) -> None:
    response = api_client.post(
        "/api/v1/test/principal-no-body",
        headers={
            "Authorization": f"Bearer {LOGIN_SECRET}",
            "Content-Type": "application/json",
        },
        content=content,
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": 7}


def test_key_for_missing_user_is_rejected_and_stale_cookie_is_cleared(
    api_client: TestClient,
    services: Any,
) -> None:
    services.user.user = User(id=8, email="other@example.com")

    response = api_client.get(
        "/api/v1/test/principal",
        headers={"Cookie": _cookie_header(LOGIN_SECRET)},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    assert any(value.startswith(f"{ACCESS_COOKIE_NAME}=") for value in response.headers.get_list("set-cookie"))


def test_custom_development_access_cookie_name_is_honored(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rentivo.api.authentication as authentication

    monkeypatch.setattr(authentication.settings, "access_cookie_name", "rentivo_access")

    response = api_client.get(
        "/api/v1/test/principal",
        headers={"Cookie": f"rentivo_access={LOGIN_SECRET}"},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "web"


def test_non_ascii_dual_credentials_return_stable_ambiguity_problem(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/test/principal",
        headers={
            b"Cookie": _cookie_header(f"{LOGIN_SECRET}é").encode(),
            b"Authorization": f"Bearer {LOGIN_SECRET}".encode(),
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "ambiguous_credentials"
