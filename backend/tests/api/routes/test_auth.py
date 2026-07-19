from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.responses import Response

from rentivo.api.app import create_app
from rentivo.api.authentication import ACCESS_COOKIE_NAME
from rentivo.api.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, issue_csrf_token
from rentivo.api.dependencies import get_services
from rentivo.api.principal import Principal
from rentivo.constants.api_scopes import ALL_FIRST_PARTY_SCOPES
from rentivo.models.api_key import APIKey
from rentivo.models.audit_log import AuditEventType
from rentivo.models.user import User
from rentivo.services.user_service import UserAlreadyRegisteredError
from rentivo.settings import settings

ACCESS_SECRET = f"rntv-v1-{'A' * 43}"
SECOND_ACCESS_SECRET = f"rntv-v1-{'B' * 43}"
INTEGRATION_SECRET = f"rntv-v1-{'I' * 43}"
CHALLENGE_NONCE = "challenge-cookie-nonce"
CHALLENGE_ID = "01J00000000000000000000000"
VALID_RESET_TOKEN = "valid-reset-token"
RESET_TOKEN_RETURNED_BY_SERVICE = "reset-token-that-must-not-be-disclosed"

USER = User(id=7, email="person@example.com")
BOOTSTRAP = {
    "user": {"id": 7, "email": "person@example.com"},
    "capabilities": {
        "scopes": ["profile:read", "security:manage"],
        "mfa_setup_required": False,
    },
    "pending_invite_count": 2,
    "feature_flags": {
        "google_auth": True,
        "turnstile": True,
        "turnstile_site_key": "turnstile-site-key",
    },
    "analytics": {"gtm_container_id": "GTM-TEST123"},
}


def _key(*, key_id: int, uuid: str, is_login_token: bool) -> APIKey:
    return APIKey(
        id=key_id,
        uuid=uuid,
        user_id=USER.id,
        name="Browser" if is_login_token else "Integration",
        secret_hash=bytes([key_id]) * 32,
        key_start="abcd",
        key_end="yz",
        is_login_token=is_login_token,
        scopes=ALL_FIRST_PARTY_SCOPES if is_login_token else frozenset({"profile:read"}),
        expires_at=datetime(2026, 7, 18, 12, tzinfo=UTC),
    )


LOGIN_KEY = _key(key_id=1, uuid="login-key-uuid", is_login_token=True)
SECOND_LOGIN_KEY = _key(key_id=2, uuid="second-login-key-uuid", is_login_token=True)
INTEGRATION_KEY = _key(key_id=3, uuid="integration-key-uuid", is_login_token=False)


@dataclass(frozen=True, slots=True)
class FakeLoginResult:
    status: str
    bootstrap: dict[str, Any] | None = None
    user: User | None = None
    api_key: APIKey | None = None
    access_credential: str | None = None
    challenge_id: str | None = None
    methods: tuple[str, ...] = ()
    challenge_nonce: str | None = None
    analytics_event: dict[str, Any] | None = None


AUTHENTICATED_RESULT = FakeLoginResult(
    status="authenticated",
    bootstrap=BOOTSTRAP,
    user=USER,
    api_key=LOGIN_KEY,
    access_credential=ACCESS_SECRET,
    analytics_event={"event": "rentivo_login_success", "via": "password"},
)
MFA_RESULT = FakeLoginResult(
    status="mfa_required",
    challenge_id=CHALLENGE_ID,
    methods=("totp", "recovery", "passkey"),
    challenge_nonce=CHALLENGE_NONCE,
)


class FakeLoginService:
    def __init__(self) -> None:
        self.login_result: FakeLoginResult | None = AUTHENTICATED_RESULT
        self.signup_result: FakeLoginResult | None = AUTHENTICATED_RESULT
        self.reject_login = False
        self.reject_signup = False
        self.login_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.signup_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.bootstrap_calls: list[str] = []

    def login(self, *args: Any, **kwargs: Any) -> FakeLoginResult | None:
        self.login_calls.append((args, kwargs))
        if self.reject_login:
            from rentivo.api.errors import ProblemException

            raise ProblemException.unauthorized("invalid_credentials", "E-mail ou senha inválidos.")
        return self.login_result

    def signup(self, *args: Any, **kwargs: Any) -> FakeLoginResult:
        self.signup_calls.append((args, kwargs))
        if self.reject_signup:
            raise UserAlreadyRegisteredError("duplicate")
        assert self.signup_result is not None
        return self.signup_result

    def bootstrap(self, principal: Principal) -> dict[str, Any]:
        self.bootstrap_calls.append(principal.api_key.uuid)
        return BOOTSTRAP


class FakeAPIKeyService:
    def __init__(self) -> None:
        self.keys = {
            ACCESS_SECRET: LOGIN_KEY,
            SECOND_ACCESS_SECRET: SECOND_LOGIN_KEY,
            INTEGRATION_SECRET: INTEGRATION_KEY,
        }
        self.logout_calls: list[str] = []
        self.revoke_all_login_calls: list[int] = []

    def authenticate(self, secret: str) -> APIKey | None:
        return self.keys.get(secret)

    def logout(self, key: APIKey) -> bool:
        self.logout_calls.append(key.uuid)
        for secret, candidate in tuple(self.keys.items()):
            if candidate.uuid == key.uuid:
                del self.keys[secret]
        return True

    def revoke_all_logins(self, user_id: int) -> int:
        self.revoke_all_login_calls.append(user_id)
        login_secrets = [secret for secret, key in self.keys.items() if key.user_id == user_id and key.is_login_token]
        for secret in login_secrets:
            del self.keys[secret]
        return len(login_secrets)


class FakeUserService:
    def get_by_id(self, user_id: int) -> User | None:
        return USER if user_id == USER.id else None


class FakeMFAService:
    def __init__(self) -> None:
        self.setup_required = False

    def user_requires_mfa_setup(self, user_id: int) -> bool:
        assert user_id == USER.id
        return self.setup_required


class FakePasswordResetService:
    def __init__(self) -> None:
        self.request_calls: list[str] = []
        self.consume_calls: list[tuple[str, str]] = []
        self.raise_for_email: str | None = None
        self.api_key_service: FakeAPIKeyService | None = None

    def request_reset(self, email: str) -> str | None:
        self.request_calls.append(email)
        if email == self.raise_for_email:
            raise RuntimeError("dispatch failed")
        if email == USER.email:
            return RESET_TOKEN_RETURNED_BY_SERVICE
        return None

    def consume(self, raw_token: str, new_password: str) -> int | None:
        self.consume_calls.append((raw_token, new_password))
        if raw_token != VALID_RESET_TOKEN:
            return None
        assert self.api_key_service is not None
        self.api_key_service.revoke_all_logins(USER.id)
        return USER.id


class FakeTurnstileService:
    def __init__(self) -> None:
        self.allowed = True
        self.is_enabled = True
        self.site_key = "turnstile-site-key"

    async def verify(self, token: str, remote_ip: str) -> bool:
        return self.allowed and (not self.is_enabled or bool(token)) and remote_ip == "testclient"


class FakeJobService:
    def __init__(self) -> None:
        self.raise_on_enqueue = False

    def enqueue_for(self, *args: Any, **kwargs: Any) -> None:
        if self.raise_on_enqueue:
            raise RuntimeError("dispatch failed")


class FakeAuditService:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def safe_log_for(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


class FakeRateLimitService:
    def __init__(self) -> None:
        self.attempts: dict[tuple[str, str], int] = {}
        self.calls: list[tuple[str, str]] = []

    def reserve(self, *, action: str, identity: str, limit: int, window_seconds: int) -> bool:
        assert window_seconds == 60
        key = (action, identity)
        self.calls.append(key)
        attempts = self.attempts.get(key, 0)
        if attempts >= limit:
            return False
        self.attempts[key] = attempts + 1
        return True

    def clear(self, *, action: str, identity: str) -> None:
        self.attempts.pop((action, identity), None)


@dataclass(slots=True)
class AuthHarness:
    client: TestClient
    app: Any
    login: FakeLoginService
    mfa: FakeMFAService
    api_key: FakeAPIKeyService
    password_reset: FakePasswordResetService
    turnstile: FakeTurnstileService
    job: FakeJobService
    audit: FakeAuditService
    rate_limit: FakeRateLimitService


@pytest.fixture()
def auth_harness(monkeypatch: pytest.MonkeyPatch) -> AuthHarness:
    import rentivo.api.csrf as csrf

    monkeypatch.setattr(settings, "secret_key", "auth-route-contract-signing-key")
    monkeypatch.setattr(settings, "access_cookie_name", "__Host-rentivo_access")
    monkeypatch.setattr(settings, "challenge_cookie_name", "__Host-rentivo_challenge")
    monkeypatch.setattr(settings, "csrf_cookie_name", "__Host-rentivo_csrf")
    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(csrf.secrets, "token_urlsafe", lambda _size: "deterministic-csrf-nonce")

    login = FakeLoginService()
    mfa = FakeMFAService()
    api_key = FakeAPIKeyService()
    password_reset = FakePasswordResetService()
    turnstile = FakeTurnstileService()
    job = FakeJobService()
    audit = FakeAuditService()
    rate_limit = FakeRateLimitService()
    password_reset.api_key_service = api_key
    services = SimpleNamespace(
        login=login,
        mfa=mfa,
        api_key=api_key,
        user=FakeUserService(),
        password_reset=password_reset,
        turnstile=turnstile,
        audit=audit,
        job=job,
        google_auth=SimpleNamespace(is_enabled=True),
        auth_rate_limit=rate_limit,
    )
    app = create_app()
    app.dependency_overrides[get_services] = lambda: services
    return AuthHarness(
        client=TestClient(app),
        app=app,
        login=login,
        mfa=mfa,
        api_key=api_key,
        password_reset=password_reset,
        turnstile=turnstile,
        job=job,
        audit=audit,
        rate_limit=rate_limit,
    )


def _cookie_header(
    access_secret: str,
    *,
    csrf_token: str | None = None,
    challenge_nonce: str | None = None,
) -> str:
    values = [f"{settings.access_cookie_name}={access_secret}"]
    if csrf_token is not None:
        values.append(f"{settings.csrf_cookie_name}={csrf_token}")
    if challenge_nonce is not None:
        values.append(f"{settings.challenge_cookie_name}={challenge_nonce}")
    return "; ".join(values)


def _cookie_line(response: Any, cookie_name: str) -> str:
    matches = [value for value in response.headers.get_list("set-cookie") if value.startswith(f"{cookie_name}=")]
    assert len(matches) == 1
    return matches[0]


def _assert_secure_host_cookie(
    line: str,
    *,
    http_only: bool,
    max_age: int | None = None,
) -> None:
    assert "; Path=/" in line
    assert "; Secure" in line
    assert "; SameSite=lax" in line
    assert "Domain=" not in line
    assert ("; HttpOnly" in line) is http_only
    if max_age is not None:
        assert f"Max-Age={max_age}" in line


def _assert_deleted_cookie(response: Any, cookie_name: str, *, http_only: bool) -> None:
    line = _cookie_line(response, cookie_name)
    assert line.startswith((f"{cookie_name}=;", f'{cookie_name}="";'))
    assert "Max-Age=0" in line
    _assert_secure_host_cookie(line, http_only=http_only)


def _assert_no_auth_secret(payload: Any) -> None:
    text = str(payload)
    assert "rntv-v1-" not in text
    assert CHALLENGE_NONCE not in text
    assert RESET_TOKEN_RETURNED_BY_SERVICE not in text


def _csrf_token_for(key: APIKey = LOGIN_KEY) -> str:
    principal = Principal(user=USER, api_key=key, source="web")
    return issue_csrf_token(Response(), principal)


def test_signup_returns_authenticated_bootstrap_and_secure_login_cookies(
    auth_harness: AuthHarness,
) -> None:
    response = auth_harness.client.post(
        "/api/v1/auth/signup",
        json={
            "email": " person@example.com ",
            "password": "correct horse battery staple",
            "confirm_password": "correct horse battery staple",
            "turnstile_token": "signup-turnstile",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "authenticated"
    assert response.json()["bootstrap"]["user"] == BOOTSTRAP["user"]
    assert response.json()["bootstrap"]["csrf_token"] == response.cookies[CSRF_COOKIE_NAME]
    _assert_no_auth_secret(response.json())
    _assert_secure_host_cookie(
        _cookie_line(response, ACCESS_COOKIE_NAME),
        http_only=True,
        max_age=24 * 60 * 60,
    )
    _assert_secure_host_cookie(_cookie_line(response, CSRF_COOKIE_NAME), http_only=False)
    assert len(auth_harness.login.signup_calls) == 1


def test_password_login_without_mfa_returns_200_and_never_serializes_the_key(
    auth_harness: AuthHarness,
) -> None:
    response = auth_harness.client.post(
        "/api/v1/auth/login",
        json={
            "email": USER.email,
            "password": "correct",
            "turnstile_token": "login-turnstile",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "authenticated"
    assert response.json()["bootstrap"]["user"] == BOOTSTRAP["user"]
    assert response.cookies[ACCESS_COOKIE_NAME] == ACCESS_SECRET
    assert response.json()["bootstrap"]["csrf_token"] == response.cookies[CSRF_COOKIE_NAME]
    assert response.json()["bootstrap"]["analytics"]["events"] == [
        {"event": "rentivo_login_success", "via": "password", "reason": None}
    ]
    _assert_no_auth_secret(response.json())
    assert response.headers["cache-control"] == "no-store"


def test_password_login_with_mfa_returns_202_and_only_discloses_public_challenge_data(
    auth_harness: AuthHarness,
) -> None:
    auth_harness.login.login_result = MFA_RESULT

    response = auth_harness.client.post(
        "/api/v1/auth/login",
        json={
            "email": USER.email,
            "password": "correct",
            "turnstile_token": "login-turnstile",
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "status": "mfa_required",
        "challenge_id": CHALLENGE_ID,
        "methods": ["totp", "recovery", "passkey"],
    }
    assert ACCESS_COOKIE_NAME not in response.cookies
    assert CSRF_COOKIE_NAME not in response.cookies
    assert response.cookies[settings.challenge_cookie_name] == CHALLENGE_NONCE
    _assert_no_auth_secret(response.json())
    _assert_secure_host_cookie(
        _cookie_line(response, settings.challenge_cookie_name),
        http_only=True,
        max_age=5 * 60,
    )
    assert response.headers["cache-control"] == "no-store"


def test_unknown_email_and_wrong_password_share_the_same_login_problem(
    auth_harness: AuthHarness,
) -> None:
    auth_harness.login.reject_login = True
    responses = [
        auth_harness.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password, "turnstile_token": "turnstile"},
            headers={"X-Request-ID": "auth-route-contract"},
        )
        for email, password in [
            ("unknown@example.com", "anything"),
            (USER.email, "wrong"),
        ]
    ]

    assert [response.status_code for response in responses] == [401, 401]
    assert responses[0].json() == responses[1].json()
    assert responses[0].json()["code"] == "invalid_credentials"
    assert responses[0].json()["detail"] == "E-mail ou senha inválidos."
    assert "unknown@example.com" not in responses[0].text
    assert [args[1] for args, _kwargs in auth_harness.audit.calls] == [
        AuditEventType.USER_LOGIN_FAILED,
        AuditEventType.USER_LOGIN_FAILED,
    ]
    assert responses[0].headers["X-Rentivo-Analytics-Event"] == "rentivo_login_failed"
    assert responses[0].headers["X-Rentivo-Analytics-Reason"] == "bad_credentials"


def test_session_returns_login_bootstrap_without_exposing_the_cookie_credential(
    auth_harness: AuthHarness,
) -> None:
    response = auth_harness.client.get(
        "/api/v1/auth/session",
        headers={"Cookie": _cookie_header(ACCESS_SECRET)},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "authenticated"
    assert response.json()["bootstrap"]["user"] == BOOTSTRAP["user"]
    assert response.json()["bootstrap"]["csrf_token"] == response.cookies[CSRF_COOKIE_NAME]
    _assert_no_auth_secret(response.json())
    assert auth_harness.login.bootstrap_calls == [LOGIN_KEY.uuid]
    _assert_deleted_cookie(response, "session", http_only=True)


def test_required_mfa_session_remains_available_for_live_bootstrap(
    auth_harness: AuthHarness,
) -> None:
    auth_harness.mfa.setup_required = True

    response = auth_harness.client.get(
        "/api/v1/auth/session",
        headers={"Cookie": _cookie_header(ACCESS_SECRET)},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "authenticated"


def test_session_requires_authentication(auth_harness: AuthHarness) -> None:
    response = auth_harness.client.get("/api/v1/auth/session")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
    _assert_deleted_cookie(response, "session", http_only=True)


@pytest.mark.parametrize(
    ("path", "headers"),
    [
        ("/api/v1/auth/session?access_token=outside", {}),
        ("/api/v1/auth/session", {"Authorization": "Bearer"}),
    ],
)
def test_rejected_session_credentials_still_expire_the_legacy_cookie(
    auth_harness: AuthHarness,
    path: str,
    headers: dict[str, str],
) -> None:
    response = auth_harness.client.get(path, headers=headers)

    assert response.status_code == 400
    assert response.json()["code"] == "malformed_credentials"
    _assert_deleted_cookie(response, "session", http_only=True)


@pytest.mark.parametrize("path", ["/api/v1/auth/session", "/api/v1/auth/csrf"])
def test_integration_keys_cannot_use_interactive_login_endpoints(
    auth_harness: AuthHarness,
    path: str,
) -> None:
    response = auth_harness.client.get(
        path,
        headers={"Authorization": f"Bearer {INTEGRATION_SECRET}"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "login_token_required"
    if path.endswith("/session"):
        _assert_deleted_cookie(response, "session", http_only=True)


def test_logout_deletes_only_the_current_login_key_and_clears_browser_cookies(
    auth_harness: AuthHarness,
) -> None:
    csrf_token = _csrf_token_for()

    response = auth_harness.client.post(
        "/api/v1/auth/logout",
        headers={
            "Cookie": _cookie_header(ACCESS_SECRET, csrf_token=csrf_token),
            CSRF_HEADER_NAME: csrf_token,
        },
    )

    assert response.status_code == 204
    assert response.content == b""
    assert auth_harness.api_key.logout_calls == [LOGIN_KEY.uuid]
    assert auth_harness.api_key.revoke_all_login_calls == []
    assert response.headers["X-Rentivo-Analytics-Event"] == "rentivo_logout"
    _assert_deleted_cookie(response, ACCESS_COOKIE_NAME, http_only=True)
    _assert_deleted_cookie(response, CSRF_COOKIE_NAME, http_only=False)

    other_session = auth_harness.client.get(
        "/api/v1/auth/session",
        headers={"Cookie": _cookie_header(SECOND_ACCESS_SECRET)},
    )
    assert other_session.status_code == 200


def test_required_mfa_user_can_still_logout(auth_harness: AuthHarness) -> None:
    auth_harness.mfa.setup_required = True
    csrf_token = _csrf_token_for()

    response = auth_harness.client.post(
        "/api/v1/auth/logout",
        headers={
            "Cookie": _cookie_header(ACCESS_SECRET, csrf_token=csrf_token),
            CSRF_HEADER_NAME: csrf_token,
        },
    )

    assert response.status_code == 204
    assert auth_harness.api_key.logout_calls == [LOGIN_KEY.uuid]


def test_cookie_authenticated_logout_requires_csrf_before_deleting_the_key(
    auth_harness: AuthHarness,
) -> None:
    response = auth_harness.client.post(
        "/api/v1/auth/logout",
        headers={"Cookie": _cookie_header(ACCESS_SECRET)},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    assert auth_harness.api_key.logout_calls == []


def test_integration_key_cannot_call_logout(auth_harness: AuthHarness) -> None:
    response = auth_harness.client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {INTEGRATION_SECRET}"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "login_token_required"
    assert auth_harness.api_key.logout_calls == []


def test_password_forgot_is_identical_for_known_and_unknown_email(
    auth_harness: AuthHarness,
) -> None:
    responses = [
        auth_harness.client.post(
            "/api/v1/auth/password/forgot",
            json={"email": email, "turnstile_token": "forgot-turnstile"},
        )
        for email in [USER.email, "unknown@example.com"]
    ]

    assert [response.status_code for response in responses] == [202, 202]
    assert (
        responses[0].json()
        == responses[1].json()
        == {
            "status": "accepted",
            "analytics_events": [{"event": "rentivo_password_reset_requested", "via": None, "reason": None}],
        }
    )
    assert RESET_TOKEN_RETURNED_BY_SERVICE not in responses[0].text
    assert USER.email not in responses[0].text
    assert auth_harness.password_reset.request_calls == [USER.email, "unknown@example.com"]


def test_password_forgot_does_not_disclose_dispatch_failure(
    auth_harness: AuthHarness,
) -> None:
    auth_harness.password_reset.raise_for_email = USER.email

    response = auth_harness.client.post(
        "/api/v1/auth/password/forgot",
        json={"email": USER.email, "turnstile_token": "forgot-turnstile"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"


def test_password_reset_revokes_every_login_key_but_not_integration_keys(
    auth_harness: AuthHarness,
) -> None:
    response = auth_harness.client.post(
        "/api/v1/auth/password/reset",
        json={
            "token": VALID_RESET_TOKEN,
            "password": "new-password",
            "confirm_password": "new-password",
        },
        headers={
            "Cookie": _cookie_header(
                ACCESS_SECRET,
                csrf_token="stale-csrf",
                challenge_nonce="stale-challenge",
            )
        },
    )

    assert response.status_code == 204
    assert response.content == b""
    assert auth_harness.password_reset.consume_calls == [(VALID_RESET_TOKEN, "new-password")]
    assert auth_harness.api_key.revoke_all_login_calls == [USER.id]
    assert INTEGRATION_SECRET in auth_harness.api_key.keys
    assert ACCESS_SECRET not in auth_harness.api_key.keys
    assert SECOND_ACCESS_SECRET not in auth_harness.api_key.keys
    _assert_deleted_cookie(response, ACCESS_COOKIE_NAME, http_only=True)
    _assert_deleted_cookie(response, CSRF_COOKIE_NAME, http_only=False)
    _assert_deleted_cookie(response, settings.challenge_cookie_name, http_only=True)


def test_invalid_and_expired_password_reset_tokens_share_one_problem(
    auth_harness: AuthHarness,
) -> None:
    responses = [
        auth_harness.client.post(
            "/api/v1/auth/password/reset",
            json={"token": token, "password": "new-password", "confirm_password": "new-password"},
            headers={"X-Request-ID": "auth-route-contract"},
        )
        for token in ["unknown-token", "expired-token"]
    ]

    assert [response.status_code for response in responses] == [400, 400]
    assert responses[0].json() == responses[1].json()
    assert responses[0].json()["code"] == "invalid_or_expired_reset_token"
    assert "unknown-token" not in responses[0].text
    assert "expired-token" not in responses[1].text
    assert auth_harness.api_key.revoke_all_login_calls == []


def test_csrf_endpoint_returns_bound_token_in_a_secure_non_http_only_cookie(
    auth_harness: AuthHarness,
) -> None:
    response = auth_harness.client.get(
        "/api/v1/auth/csrf",
        headers={"Cookie": _cookie_header(ACCESS_SECRET)},
    )

    assert response.status_code == 200
    assert response.json() == {"csrf_token": response.cookies[CSRF_COOKIE_NAME]}
    _assert_no_auth_secret(response.json())
    _assert_secure_host_cookie(_cookie_line(response, CSRF_COOKIE_NAME), http_only=False)
    assert response.headers["cache-control"] == "no-store"


def test_auth_openapi_exposes_versioned_json_operations_and_both_login_outcomes(
    auth_harness: AuthHarness,
) -> None:
    schema = auth_harness.app.openapi()
    expected = {
        "/api/v1/auth/signup": "post",
        "/api/v1/auth/login": "post",
        "/api/v1/auth/session": "get",
        "/api/v1/auth/logout": "post",
        "/api/v1/auth/password/forgot": "post",
        "/api/v1/auth/password/reset": "post",
        "/api/v1/auth/csrf": "get",
        "/api/v1/auth/config": "get",
    }

    for path, method in expected.items():
        operation = schema["paths"][path][method]
        assert operation["operationId"]
        assert "auth" in operation["tags"]

    login_operation = schema["paths"]["/api/v1/auth/login"]["post"]
    assert "application/json" in login_operation["requestBody"]["content"]
    assert {"200", "202", "422"}.issubset(login_operation["responses"])
    assert schema["paths"]["/api/v1/auth/logout"]["post"]["responses"].get("204") is not None
    bootstrap_schema = schema["components"]["schemas"]["BootstrapResponse"]
    assert bootstrap_schema["additionalProperties"] is False


def test_turnstile_failure_stops_login_before_credentials(auth_harness: AuthHarness) -> None:
    auth_harness.turnstile.allowed = False

    response = auth_harness.client.post(
        "/api/v1/auth/login",
        json={"email": USER.email, "password": "correct", "turnstile_token": "invalid"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "turnstile_failed"
    assert auth_harness.login.login_calls == []
    assert auth_harness.rate_limit.calls == []


def test_disabled_turnstile_accepts_an_omitted_token(auth_harness: AuthHarness) -> None:
    auth_harness.turnstile.is_enabled = False

    response = auth_harness.client.post(
        "/api/v1/auth/login",
        json={"email": USER.email, "password": "correct"},
    )

    assert response.status_code == 200
    assert auth_harness.login.login_calls[0][1]["password"] == "correct"


def test_public_auth_config_exposes_only_browser_safe_settings(auth_harness: AuthHarness) -> None:
    response = auth_harness.client.get("/api/v1/auth/config")

    assert response.status_code == 200
    assert response.json() == {
        "feature_flags": {
            "google_auth": True,
            "turnstile": True,
            "turnstile_site_key": "turnstile-site-key",
        },
        "analytics": {"gtm_container_id": settings.gtm_container_id},
    }
    assert "secret" not in response.text.lower()


def test_authentication_preserves_password_whitespace(auth_harness: AuthHarness) -> None:
    response = auth_harness.client.post(
        "/api/v1/auth/login",
        json={
            "email": " PERSON@example.com ",
            "password": "  intentional whitespace  ",
            "turnstile_token": "turnstile",
        },
    )

    assert response.status_code == 200
    assert auth_harness.login.login_calls[0][1]["email"] == USER.email
    assert auth_harness.login.login_calls[0][1]["password"] == "  intentional whitespace  "


def test_duplicate_signup_returns_stable_problem(auth_harness: AuthHarness) -> None:
    auth_harness.login.reject_signup = True

    response = auth_harness.client.post(
        "/api/v1/auth/signup",
        json={
            "email": USER.email,
            "password": "password",
            "confirm_password": "password",
            "turnstile_token": "turnstile",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "email_already_registered"


def test_login_rate_limit_is_preserved_for_none_results(auth_harness: AuthHarness) -> None:
    auth_harness.login.login_result = None
    payload = {"email": USER.email, "password": "wrong", "turnstile_token": "turnstile"}

    failures = [auth_harness.client.post("/api/v1/auth/login", json=payload) for _ in range(5)]
    limited = auth_harness.client.post("/api/v1/auth/login", json=payload)

    assert [response.status_code for response in failures] == [401] * 5
    assert limited.status_code == 429
    assert limited.json()["code"] == "login_rate_limited"
    assert limited.headers["X-Rentivo-Analytics-Reason"] == "rate_limited"


def test_login_preserves_noncredential_problem_exceptions(auth_harness: AuthHarness) -> None:
    from rentivo.api.errors import ProblemException

    auth_harness.login.login = MagicMock(
        side_effect=ProblemException.forbidden("account_disabled", "Conta indisponível.")
    )

    response = auth_harness.client.post(
        "/api/v1/auth/login",
        json={"email": USER.email, "password": "correct", "turnstile_token": "token"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "account_disabled"


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/auth/signup",
            {
                "email": "",
                "password": "password",
                "confirm_password": "different",
                "turnstile_token": "token",
            },
        ),
        (
            "/api/v1/auth/login",
            {"email": "", "password": "password", "turnstile_token": "token"},
        ),
        (
            "/api/v1/auth/password/forgot",
            {"email": "", "turnstile_token": "token"},
        ),
        (
            "/api/v1/auth/password/reset",
            {"token": "token", "password": "password", "confirm_password": "different"},
        ),
    ],
)
def test_auth_schema_validation_is_stable(
    auth_harness: AuthHarness,
    path: str,
    payload: dict[str, str],
) -> None:
    response = auth_harness.client.post(path, json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_signup_rejects_nonblank_password_mismatch(auth_harness: AuthHarness) -> None:
    response = auth_harness.client.post(
        "/api/v1/auth/signup",
        json={
            "email": USER.email,
            "password": "password-one",
            "confirm_password": "password-two",
            "turnstile_token": "token",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_password_reset_confirmation_dispatch_failure_does_not_change_success(
    auth_harness: AuthHarness,
) -> None:
    auth_harness.job.raise_on_enqueue = True

    response = auth_harness.client.post(
        "/api/v1/auth/password/reset",
        json={
            "token": VALID_RESET_TOKEN,
            "password": "new-password",
            "confirm_password": "new-password",
        },
    )

    assert response.status_code == 204
    assert auth_harness.api_key.revoke_all_login_calls == [USER.id]


@pytest.mark.parametrize(
    "result",
    [
        FakeLoginResult(status="authenticated", bootstrap=BOOTSTRAP),
        FakeLoginResult(
            status="authenticated",
            bootstrap=BOOTSTRAP,
            user=USER,
            api_key=LOGIN_KEY,
        ),
        FakeLoginResult(status="mfa_required", challenge_id=CHALLENGE_ID),
    ],
)
def test_incomplete_internal_login_results_fail_closed(
    auth_harness: AuthHarness,
    result: FakeLoginResult,
) -> None:
    auth_harness.login.login_result = result

    with pytest.raises(RuntimeError):
        auth_harness.client.post(
            "/api/v1/auth/login",
            json={"email": USER.email, "password": "correct", "turnstile_token": "token"},
        )


def test_auth_routes_reject_api_keys_outside_cookie_or_bearer_transport(
    auth_harness: AuthHarness,
) -> None:
    response = auth_harness.client.post(
        f"/api/v1/auth/login?api_key={ACCESS_SECRET}",
        json={"email": USER.email, "password": "correct", "turnstile_token": "token"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "malformed_credentials"
    assert auth_harness.login.login_calls == []


def test_public_auth_routes_reject_malformed_authorization(auth_harness: AuthHarness) -> None:
    response = auth_harness.client.post(
        "/api/v1/auth/login",
        json={"email": USER.email, "password": "correct", "turnstile_token": "token"},
        headers={"Authorization": ACCESS_SECRET},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "malformed_credentials"
    assert auth_harness.login.login_calls == []


def test_public_auth_routes_reject_ambiguous_credentials(auth_harness: AuthHarness) -> None:
    response = auth_harness.client.post(
        "/api/v1/auth/login",
        json={"email": USER.email, "password": "correct", "turnstile_token": "token"},
        headers={
            "Cookie": _cookie_header(ACCESS_SECRET),
            "Authorization": f"Bearer {SECOND_ACCESS_SECRET}",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "ambiguous_credentials"
    assert auth_harness.login.login_calls == []


def test_downstream_signup_value_error_is_not_misreported_as_duplicate(
    auth_harness: AuthHarness,
) -> None:
    auth_harness.login.signup = MagicMock(side_effect=ValueError("bootstrap invalid"))

    with pytest.raises(ValueError, match="bootstrap invalid"):
        auth_harness.client.post(
            "/api/v1/auth/signup",
            json={
                "email": USER.email,
                "password": "password",
                "confirm_password": "password",
                "turnstile_token": "turnstile",
            },
        )


def test_password_forgot_rate_limit_is_bounded(auth_harness: AuthHarness) -> None:
    payload = {"email": USER.email, "turnstile_token": "turnstile"}

    accepted = [auth_harness.client.post("/api/v1/auth/password/forgot", json=payload) for _ in range(5)]
    limited = auth_harness.client.post("/api/v1/auth/password/forgot", json=payload)

    assert [response.status_code for response in accepted] == [202] * 5
    assert limited.status_code == 429
    assert limited.json()["code"] == "password_reset_rate_limited"
