from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import pytest
from fastapi.testclient import TestClient

from rentivo.api.app import create_app
from rentivo.api.dependencies import get_services
from rentivo.constants.api_scopes import ALL_FIRST_PARTY_SCOPES
from rentivo.models.api_key import APIKey
from rentivo.models.audit_log import AuditEventType
from rentivo.models.auth_challenge import AuthChallenge
from rentivo.models.user import User
from rentivo.services.api_key_service import IssuedAPIKey
from rentivo.services.auth_challenge_service import IssuedAuthChallenge
from rentivo.services.google_auth_service import GoogleUserInfo
from rentivo.services.login_service import LoginResult, LoginService
from rentivo.settings import settings

NOW = datetime(2026, 7, 17, 12, tzinfo=UTC)
OAUTH_STATE = "01J00000000000000000000001"
MFA_CHALLENGE_ID = "01J00000000000000000000002"
OAUTH_NONCE = "oauth-nonce-that-must-never-be-disclosed"
MFA_NONCE = "mfa-nonce-that-must-never-be-disclosed"
ACCESS_SECRET = f"rntv-v1-{'A' * 43}"
AUTH_CODE = "google-authorization-code-secret"
USER_AGENT = "Rentivo OAuth contract browser/1.0"
EXISTING_USER = User(id=7, email="existing@example.com", password_hash="existing-password-hash")


def _challenge(*, uuid: str, user_id: int | None, phase: str, methods: tuple[str, ...]) -> AuthChallenge:
    return AuthChallenge(
        id=11 if user_id is None else 12,
        uuid=uuid,
        user_id=user_id,
        phase=phase,
        nonce_hash=b"server-side-digest-only",
        allowed_methods=methods,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )


class FakeAuthChallengeService:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.oauth_available = True
        self.issue_calls: list[dict[str, Any]] = []
        self.consume_calls: list[dict[str, Any]] = []

    def issue(self, **kwargs: Any) -> IssuedAuthChallenge:
        self.issue_calls.append(kwargs)
        phase = kwargs["phase"]
        self.events.append(f"challenge.issue:{phase}")
        if phase == "oauth":
            return IssuedAuthChallenge(
                challenge=_challenge(uuid=OAUTH_STATE, user_id=None, phase="oauth", methods=("google",)),
                nonce=OAUTH_NONCE,
            )
        return IssuedAuthChallenge(
            challenge=_challenge(
                uuid=MFA_CHALLENGE_ID,
                user_id=kwargs["user_id"],
                phase="login",
                methods=tuple(kwargs["allowed_methods"]),
            ),
            nonce=MFA_NONCE,
        )

    def consume(
        self,
        uuid: str,
        nonce: str,
        *,
        expected_phase: str,
        expected_method: str | None,
    ) -> AuthChallenge | None:
        self.events.append("challenge.consume:oauth")
        self.consume_calls.append(
            {
                "uuid": uuid,
                "nonce": nonce,
                "expected_phase": expected_phase,
                "expected_method": expected_method,
            }
        )
        valid = (
            self.oauth_available
            and uuid == OAUTH_STATE
            and nonce == OAUTH_NONCE
            and expected_phase == "oauth"
            and expected_method == "google"
        )
        if not valid:
            return None
        self.oauth_available = False
        return _challenge(uuid=OAUTH_STATE, user_id=None, phase="oauth", methods=("google",)).model_copy(
            update={"consumed_at": NOW}
        )


class FakeGoogleAuthService:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.is_enabled = True
        self.info: GoogleUserInfo | None = GoogleUserInfo(
            sub="google-subject-1",
            email=EXISTING_USER.email,
            email_verified=True,
        )
        self.authorization_states: list[str] = []
        self.exchange_calls: list[str] = []

    def build_authorization_url(self, state: str) -> str:
        self.authorization_states.append(state)
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            {
                "client_id": "test-google-client",
                "redirect_uri": "https://app.example/auth/google/callback",
                "response_type": "code",
                "scope": "openid email",
                "state": state,
                "prompt": "select_account",
            }
        )

    async def exchange_code(self, code: str) -> GoogleUserInfo | None:
        self.events.append("google.exchange")
        self.exchange_calls.append(code)
        return self.info


class FakeUserService:
    def __init__(self) -> None:
        self.users: dict[str, User] = {EXISTING_USER.email: EXISTING_USER}
        self.get_calls: list[str] = []
        self.register_calls: list[str] = []

    def get_by_email(self, email: str) -> User | None:
        self.get_calls.append(email)
        return self.users.get(email)

    def register_google_user(self, email: str) -> User:
        self.register_calls.append(email)
        if email in self.users:
            raise ValueError("duplicate")
        user = User(id=8, email=email)
        self.users[email] = user
        return user


class FakeMFAService:
    def __init__(self) -> None:
        self.has_totp = False
        self.passkeys: list[object] = []

    def has_confirmed_totp(self, _user_id: int) -> bool:
        return self.has_totp

    def has_any_mfa(self, _user_id: int) -> bool:
        return self.has_totp or bool(self.passkeys)

    def list_passkeys(self, _user_id: int) -> list[object]:
        return self.passkeys

    def user_requires_mfa_setup(self, _user_id: int) -> bool:
        return False


class FakeAPIKeyService:
    def __init__(self) -> None:
        self.issue_calls: list[dict[str, Any]] = []

    def issue_login(self, **kwargs: Any) -> IssuedAPIKey:
        self.issue_calls.append(kwargs)
        user_id = kwargs["user_id"]
        key = APIKey(
            id=21,
            uuid="01J00000000000000000000003",
            user_id=user_id,
            name=kwargs["name"],
            secret_hash=b"login-key-digest",
            key_start="AAAA",
            key_end="AA",
            is_login_token=True,
            scopes=ALL_FIRST_PARTY_SCOPES,
            expires_at=NOW + timedelta(days=1),
            created_at=NOW,
        )
        return IssuedAPIKey(key=key, secret=ACCESS_SECRET)

    def logout(self, _key: APIKey) -> bool:
        return True


class FakeAuditService:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def safe_log_for(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


class FakeKnownDeviceService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def notify_if_new(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class FakeJobService:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def enqueue_for(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


class CapturingLoginService(LoginService):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.google_calls: list[dict[str, Any]] = []
        self.google_result: LoginResult | None = None

    def login_with_google(self, **kwargs: Any) -> LoginResult:
        self.google_calls.append(kwargs)
        implementation = getattr(super(), "login_with_google")
        self.google_result = implementation(**kwargs)
        return self.google_result


@dataclass(slots=True)
class GoogleAuthHarness:
    client: TestClient
    app: Any
    events: list[str]
    auth_challenge: FakeAuthChallengeService
    google_auth: FakeGoogleAuthService
    login: CapturingLoginService
    user: FakeUserService
    mfa: FakeMFAService
    api_key: FakeAPIKeyService
    audit: FakeAuditService
    known_device: FakeKnownDeviceService
    job: FakeJobService


@pytest.fixture()
def google_harness(monkeypatch: pytest.MonkeyPatch) -> GoogleAuthHarness:
    import rentivo.api.csrf as csrf

    monkeypatch.setattr(settings, "secret_key", "google-route-contract-signing-key")
    monkeypatch.setattr(settings, "access_cookie_name", "__Host-rentivo_access")
    monkeypatch.setattr(settings, "challenge_cookie_name", "__Host-rentivo_challenge")
    monkeypatch.setattr(settings, "csrf_cookie_name", "__Host-rentivo_csrf")
    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(settings, "auth_challenge_ttl_seconds", 5 * 60)
    monkeypatch.setattr(settings, "api_key_login_ttl_seconds", 24 * 60 * 60)
    monkeypatch.setattr(csrf.secrets, "token_urlsafe", lambda _size: "deterministic-csrf-nonce")

    events: list[str] = []
    auth_challenge = FakeAuthChallengeService(events)
    google_auth = FakeGoogleAuthService(events)
    user = FakeUserService()
    mfa = FakeMFAService()
    api_key = FakeAPIKeyService()
    audit = FakeAuditService()
    known_device = FakeKnownDeviceService()
    job = FakeJobService()
    login = CapturingLoginService(
        user_service=user,
        api_key_service=api_key,
        challenge_service=auth_challenge,
        mfa_service=mfa,
        audit_service=audit,
        known_device_service=known_device,
        job_service=job,
        bootstrap_builder=lambda **kwargs: {
            "user": {"id": kwargs["user"].id, "email": kwargs["user"].email},
            "capabilities": {
                "scopes": sorted(kwargs["api_key"].scopes),
                "mfa_setup_required": kwargs["mfa_setup_required"],
            },
            "pending_invite_count": 0,
            "feature_flags": {"google_auth": True},
            "analytics": {"gtm_container_id": "GTM-CONTRACT"},
        },
        public_app_url="https://app.example",
    )
    services = SimpleNamespace(
        auth_challenge=auth_challenge,
        google_auth=google_auth,
        login=login,
        user=user,
        mfa=mfa,
        api_key=api_key,
        audit=audit,
        known_device=known_device,
        job=job,
    )
    app = create_app()
    app.dependency_overrides[get_services] = lambda: services
    return GoogleAuthHarness(
        client=TestClient(app, base_url="https://testserver"),
        app=app,
        events=events,
        auth_challenge=auth_challenge,
        google_auth=google_auth,
        login=login,
        user=user,
        mfa=mfa,
        api_key=api_key,
        audit=audit,
        known_device=known_device,
        job=job,
    )


def _cookie_lines(response: Any, cookie_name: str) -> list[str]:
    return [
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith((f"{cookie_name}=", f'"{cookie_name}"='))
    ]


def _assert_secure_host_cookie(line: str, *, http_only: bool, max_age: int | None = None) -> None:
    assert "; Path=/" in line
    assert "; Secure" in line
    assert "; SameSite=lax" in line
    assert "Domain=" not in line
    assert ("; HttpOnly" in line) is http_only
    if max_age is not None:
        assert f"Max-Age={max_age}" in line


def _assert_deleted_cookie(response: Any, cookie_name: str, *, http_only: bool) -> None:
    lines = _cookie_lines(response, cookie_name)
    assert len(lines) == 1
    assert "Max-Age=0" in lines[0]
    _assert_secure_host_cookie(lines[0], http_only=http_only)


def _callback(
    harness: GoogleAuthHarness,
    *,
    query: str = f"code={AUTH_CODE}&state={OAUTH_STATE}",
    nonce: str | None = OAUTH_NONCE,
) -> Any:
    headers = {"User-Agent": USER_AGENT}
    if nonce is not None:
        headers["Cookie"] = f"{settings.challenge_cookie_name}={nonce}"
    return harness.client.get(
        f"/api/v1/auth/google/callback?{query}",
        headers=headers,
        follow_redirects=False,
    )


def _audit_events(harness: GoogleAuthHarness) -> list[str]:
    return [args[1] for args, _kwargs in harness.audit.calls]


@pytest.mark.parametrize("path", ["/api/v1/auth/google/start", "/api/v1/auth/google/callback?code=x&state=y"])
def test_google_endpoints_are_not_available_when_provider_is_disabled(
    google_harness: GoogleAuthHarness,
    path: str,
) -> None:
    google_harness.google_auth.is_enabled = False

    response = google_harness.client.get(path, follow_redirects=False)

    assert response.status_code == 404
    assert google_harness.auth_challenge.issue_calls == []
    assert google_harness.auth_challenge.consume_calls == []
    assert google_harness.google_auth.exchange_calls == []


def test_google_start_issues_userless_oauth_challenge_and_redirects_with_only_public_state(
    google_harness: GoogleAuthHarness,
) -> None:
    response = google_harness.client.get("/api/v1/auth/google/start", follow_redirects=False)

    assert response.status_code == 302
    assert google_harness.auth_challenge.issue_calls == [
        {"user_id": None, "phase": "oauth", "allowed_methods": ("google",)}
    ]
    assert google_harness.google_auth.authorization_states == [OAUTH_STATE]
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["state"] == [OAUTH_STATE]
    assert query["redirect_uri"] == ["https://app.example/auth/google/callback"]
    assert OAUTH_NONCE not in response.headers["location"]
    assert response.headers["cache-control"] == "no-store"

    cookie_lines = _cookie_lines(response, settings.challenge_cookie_name)
    assert len(cookie_lines) == 1
    assert response.cookies[settings.challenge_cookie_name] == OAUTH_NONCE
    _assert_secure_host_cookie(cookie_lines[0], http_only=True, max_age=5 * 60)


@pytest.mark.parametrize(
    ("state", "nonce", "available"),
    [
        ("01J00000000000000000000999", OAUTH_NONCE, True),
        (OAUTH_STATE, "wrong-cookie-nonce", True),
        (OAUTH_STATE, None, True),
        (OAUTH_STATE, OAUTH_NONCE, False),
    ],
)
def test_invalid_expired_or_unbound_oauth_state_fails_before_google_exchange(
    google_harness: GoogleAuthHarness,
    state: str,
    nonce: str | None,
    available: bool,
) -> None:
    google_harness.auth_challenge.oauth_available = available

    response = _callback(google_harness, query=f"code={AUTH_CODE}&state={state}", nonce=nonce)

    assert response.status_code == 302
    assert response.headers["location"] == "/login?error=google_auth_failed"
    assert google_harness.google_auth.exchange_calls == []
    assert google_harness.login.google_calls == []
    _assert_deleted_cookie(response, settings.challenge_cookie_name, http_only=True)
    assert AUTH_CODE not in response.headers["location"]
    assert OAUTH_NONCE not in response.headers["location"]


@pytest.mark.parametrize("query", [f"error=access_denied&state={OAUTH_STATE}", f"state={OAUTH_STATE}"])
def test_provider_error_or_missing_code_consumes_valid_state_and_returns_one_generic_failure(
    google_harness: GoogleAuthHarness,
    query: str,
) -> None:
    response = _callback(google_harness, query=query)

    assert response.status_code == 302
    assert response.headers["location"] == "/login?error=google_auth_failed"
    assert google_harness.auth_challenge.consume_calls == [
        {
            "uuid": OAUTH_STATE,
            "nonce": OAUTH_NONCE,
            "expected_phase": "oauth",
            "expected_method": "google",
        }
    ]
    assert google_harness.google_auth.exchange_calls == []
    _assert_deleted_cookie(response, settings.challenge_cookie_name, http_only=True)


@pytest.mark.parametrize(
    "google_info",
    [
        None,
        GoogleUserInfo(sub="google-subject-1", email="unverified@example.com", email_verified=False),
    ],
)
def test_exchange_failure_and_unverified_email_are_non_disclosing_and_clear_oauth_cookie(
    google_harness: GoogleAuthHarness,
    google_info: GoogleUserInfo | None,
) -> None:
    google_harness.google_auth.info = google_info

    response = _callback(google_harness)

    assert response.status_code == 302
    assert response.headers["location"] == "/login?error=google_auth_failed"
    assert google_harness.events.index("challenge.consume:oauth") < google_harness.events.index("google.exchange")
    assert google_harness.login.google_calls == []
    _assert_deleted_cookie(response, settings.challenge_cookie_name, http_only=True)
    disclosed = response.text + "\n" + "\n".join(response.headers.values())
    assert AUTH_CODE not in disclosed
    assert OAUTH_NONCE not in disclosed
    assert "unverified@example.com" not in disclosed
    assert "rntv-v1-" not in disclosed


def test_existing_google_user_is_logged_in_after_atomic_state_consumption(
    google_harness: GoogleAuthHarness,
) -> None:
    response = _callback(google_harness)

    assert response.status_code == 302
    assert response.headers["location"] == "/billings/"
    assert google_harness.events.index("challenge.consume:oauth") < google_harness.events.index("google.exchange")
    assert google_harness.auth_challenge.consume_calls == [
        {
            "uuid": OAUTH_STATE,
            "nonce": OAUTH_NONCE,
            "expected_phase": "oauth",
            "expected_method": "google",
        }
    ]
    assert google_harness.login.google_calls == [
        {"email": EXISTING_USER.email, "client_ip": "testclient", "user_agent": USER_AGENT}
    ]
    assert google_harness.user.get_calls == [EXISTING_USER.email]
    assert google_harness.user.register_calls == []
    assert google_harness.api_key.issue_calls == [{"user_id": EXISTING_USER.id, "name": "Web login"}]
    assert _audit_events(google_harness) == [AuditEventType.USER_LOGIN]
    assert google_harness.audit.calls[0][1]["metadata"] == {"ip": "testclient", "method": "google"}
    assert google_harness.login.google_result is not None
    assert google_harness.login.google_result.analytics_event == {
        "event": "rentivo_login_success",
        "via": "google",
    }


def test_new_google_user_preserves_signup_audit_welcome_email_and_analytics(
    google_harness: GoogleAuthHarness,
) -> None:
    email = "new-google-user@example.com"
    google_harness.google_auth.info = GoogleUserInfo(
        sub="google-subject-new",
        email=email,
        email_verified=True,
    )

    response = _callback(google_harness)

    assert response.status_code == 302
    assert response.headers["location"] == "/billings/"
    assert google_harness.user.get_calls == [email]
    assert google_harness.user.register_calls == [email]
    assert _audit_events(google_harness) == [AuditEventType.USER_SIGNUP, AuditEventType.USER_LOGIN]
    signup_call = google_harness.audit.calls[0]
    assert signup_call[1]["metadata"] == {"method": "google"}
    login_call = google_harness.audit.calls[1]
    assert login_call[1]["metadata"] == {"ip": "testclient", "method": "google"}
    assert len(google_harness.job.calls) == 1
    _actor, job_type, payload = google_harness.job.calls[0][0]
    assert job_type == "email.send"
    assert payload == {
        "event": "welcome",
        "to_email": email,
        "ctx": {"email": email, "pix_setup_url": "https://app.example/security/pix"},
    }
    assert google_harness.login.google_result is not None
    assert google_harness.login.google_result.analytics_event == {
        "event": "rentivo_signup_completed",
        "via": "google",
    }


def test_google_login_without_mfa_issues_access_and_csrf_and_clears_oauth_cookie(
    google_harness: GoogleAuthHarness,
) -> None:
    response = _callback(google_harness)

    assert response.cookies[settings.access_cookie_name] == ACCESS_SECRET
    assert response.cookies[settings.csrf_cookie_name]
    access_lines = _cookie_lines(response, settings.access_cookie_name)
    csrf_lines = _cookie_lines(response, settings.csrf_cookie_name)
    assert len(access_lines) == len(csrf_lines) == 1
    _assert_secure_host_cookie(access_lines[0], http_only=True, max_age=24 * 60 * 60)
    _assert_secure_host_cookie(csrf_lines[0], http_only=False)
    _assert_deleted_cookie(response, settings.challenge_cookie_name, http_only=True)
    assert ACCESS_SECRET not in response.text
    assert ACCESS_SECRET not in response.headers["location"]


def test_google_login_with_mfa_replaces_oauth_cookie_and_redirects_with_public_challenge_only(
    google_harness: GoogleAuthHarness,
) -> None:
    google_harness.mfa.has_totp = True

    response = _callback(google_harness)

    assert response.status_code == 302
    assert response.headers["location"] == f"/mfa-verify?challenge={MFA_CHALLENGE_ID}"
    assert google_harness.auth_challenge.issue_calls == [
        {
            "user_id": EXISTING_USER.id,
            "phase": "login",
            "allowed_methods": ("totp", "recovery"),
        }
    ]
    assert google_harness.api_key.issue_calls == []
    assert settings.access_cookie_name not in response.cookies
    assert settings.csrf_cookie_name not in response.cookies
    assert response.cookies[settings.challenge_cookie_name] == MFA_NONCE
    challenge_lines = _cookie_lines(response, settings.challenge_cookie_name)
    assert len(challenge_lines) == 1
    _assert_secure_host_cookie(challenge_lines[0], http_only=True, max_age=5 * 60)
    assert OAUTH_NONCE not in challenge_lines[0]
    assert MFA_NONCE not in response.headers["location"]
    assert _audit_events(google_harness) == [AuditEventType.MFA_CHALLENGE_ISSUED]
    assert google_harness.audit.calls[0][1]["metadata"] == {"ip": "testclient", "method": "google"}


def test_google_callback_rejects_an_incomplete_internal_mfa_result(
    google_harness: GoogleAuthHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        google_harness.login,
        "login_with_google",
        lambda **_kwargs: SimpleNamespace(
            status="mfa_required",
            challenge_id=None,
            challenge_nonce=None,
        ),
    )

    with pytest.raises(RuntimeError, match="Google MFA result is incomplete"):
        _callback(google_harness)


def test_replayed_google_callback_cannot_exchange_code_or_issue_a_second_login_key(
    google_harness: GoogleAuthHarness,
) -> None:
    first = _callback(google_harness)
    second = _callback(google_harness)

    assert first.status_code == 302
    assert first.headers["location"] == "/billings/"
    assert second.status_code == 302
    assert second.headers["location"] == "/login?error=google_auth_failed"
    assert google_harness.google_auth.exchange_calls == [AUTH_CODE]
    assert google_harness.api_key.issue_calls == [{"user_id": EXISTING_USER.id, "name": "Web login"}]
    assert len(google_harness.auth_challenge.consume_calls) == 2
    _assert_deleted_cookie(second, settings.challenge_cookie_name, http_only=True)


def test_google_oauth_operations_are_exposed_in_openapi(google_harness: GoogleAuthHarness) -> None:
    schema = google_harness.app.openapi()

    for path in ["/api/v1/auth/google/start", "/api/v1/auth/google/callback"]:
        operation = schema["paths"][path]["get"]
        assert operation["operationId"]
        assert "auth" in operation["tags"]
