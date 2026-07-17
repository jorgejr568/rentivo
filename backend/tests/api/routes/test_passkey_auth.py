from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
import webauthn
from fastapi.testclient import TestClient

from rentivo.api.app import create_app
from rentivo.api.dependencies import get_services
from rentivo.constants.api_scopes import ALL_FIRST_PARTY_SCOPES
from rentivo.models.api_key import APIKey
from rentivo.models.audit_log import AuditEventType
from rentivo.models.auth_challenge import AuthChallenge
from rentivo.models.mfa import UserPasskey
from rentivo.models.user import User
from rentivo.settings import settings

CHALLENGE_ID = "01K0PASSKEYCHALLENGE0000000"
CHALLENGE_NONCE = "passkey-challenge-cookie-nonce"
SERVER_CHALLENGE = b"deterministic-server-webauthn-challenge"
ACCESS_SECRET = f"rntv-v1-{'P' * 43}"
CREDENTIAL_ID = "Y3JlZGVudGlhbC1pZA"
PUBLIC_KEY = "cHVibGljLWtleQ"
NOW = datetime(2026, 7, 17, 12, tzinfo=UTC)

USER = User(id=9, email="passkey-user@example.com")
OTHER_USER = User(id=10, email="other-passkey-user@example.com")
PASSKEY = UserPasskey(
    id=21,
    uuid="passkey-uuid",
    user_id=USER.id,
    credential_id=CREDENTIAL_ID,
    public_key=PUBLIC_KEY,
    sign_count=7,
    name="Test passkey",
)
LOGIN_KEY = APIKey(
    id=12,
    uuid="passkey-login-key-uuid",
    user_id=USER.id,
    name="Web login",
    secret_hash=b"p" * 32,
    key_start="PPPP",
    key_end="PP",
    is_login_token=True,
    scopes=ALL_FIRST_PARTY_SCOPES,
    expires_at=NOW + timedelta(days=1),
)
BOOTSTRAP = {
    "user": {"id": USER.id, "email": USER.email},
    "capabilities": {"scopes": sorted(ALL_FIRST_PARTY_SCOPES), "mfa_setup_required": False},
    "pending_invite_count": 0,
    "feature_flags": {"google_auth": True},
    "analytics": {"gtm_container_id": ""},
}
ASSERTION = {
    "id": CREDENTIAL_ID,
    "rawId": CREDENTIAL_ID,
    "type": "public-key",
    "response": {
        "authenticatorData": "YXV0aGVudGljYXRvci1kYXRh",
        "clientDataJSON": "Y2xpZW50LWRhdGE",
        "signature": "c2lnbmF0dXJl",
        "userHandle": None,
    },
}
OPTIONS_PAYLOAD = {
    "challenge": "ZGV0ZXJtaW5pc3RpYy1zZXJ2ZXItd2ViYXV0aG4tY2hhbGxlbmdl",
    "rpId": "auth.rentivo.test",
    "allowCredentials": [{"id": CREDENTIAL_ID, "type": "public-key"}],
}


def _challenge(
    *,
    phase: str = "login",
    methods: tuple[str, ...] = ("totp", "recovery", "passkey"),
    webauthn_challenge: bytes | None = SERVER_CHALLENGE,
) -> AuthChallenge:
    return AuthChallenge(
        id=4,
        uuid=CHALLENGE_ID,
        user_id=USER.id,
        phase=phase,
        nonce_hash=b"not-used-by-route-contract-tests",
        allowed_methods=methods,
        webauthn_challenge=webauthn_challenge,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )


class FakeLoginResult:
    def __init__(self) -> None:
        self.user = USER
        self.api_key = LOGIN_KEY
        self.access_credential = ACCESS_SECRET
        self.bootstrap = BOOTSTRAP


class FakeAuthChallengeService:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.challenge: AuthChallenge | None = _challenge()
        self.allow_webauthn_update = True
        self.allow_consume = True
        self.consumed = False
        self.get_valid_calls: list[tuple[str, str, str, str | None]] = []
        self.failure_calls: list[tuple[str, str, str, str | None]] = []
        self.webauthn_calls: list[tuple[str, str, str, bytes]] = []
        self.consume_calls: list[tuple[str, str, str, str | None]] = []

    def _matches(
        self,
        uuid: str,
        nonce: str,
        expected_phase: str,
        expected_method: str | None,
    ) -> bool:
        challenge = self.challenge
        return bool(
            challenge is not None
            and not self.consumed
            and challenge.expires_at > NOW
            and uuid == challenge.uuid
            and nonce == CHALLENGE_NONCE
            and challenge.phase == expected_phase
            and (expected_method is None or expected_method in challenge.allowed_methods)
        )

    def get_valid(
        self,
        uuid: str,
        nonce: str,
        *,
        expected_phase: str,
        expected_method: str | None,
    ) -> AuthChallenge | None:
        self.get_valid_calls.append((uuid, nonce, expected_phase, expected_method))
        if not self._matches(uuid, nonce, expected_phase, expected_method):
            return None
        return self.challenge

    def record_failure(
        self,
        uuid: str,
        nonce: str,
        *,
        expected_phase: str,
        expected_method: str | None,
    ) -> bool:
        self.failure_calls.append((uuid, nonce, expected_phase, expected_method))
        return self._matches(uuid, nonce, expected_phase, expected_method)

    def set_webauthn_challenge(
        self,
        uuid: str,
        nonce: str,
        *,
        expected_phase: str,
        webauthn_challenge: bytes,
    ) -> AuthChallenge | None:
        self.webauthn_calls.append((uuid, nonce, expected_phase, webauthn_challenge))
        if not self.allow_webauthn_update or not self._matches(uuid, nonce, expected_phase, "passkey"):
            return None
        assert self.challenge is not None
        self.challenge = self.challenge.model_copy(update={"webauthn_challenge": webauthn_challenge})
        return self.challenge

    def consume(
        self,
        uuid: str,
        nonce: str,
        *,
        expected_phase: str,
        expected_method: str | None,
    ) -> AuthChallenge | None:
        self.events.append("challenge.consume")
        self.consume_calls.append((uuid, nonce, expected_phase, expected_method))
        if not self.allow_consume or not self._matches(uuid, nonce, expected_phase, expected_method):
            return None
        self.consumed = True
        assert self.challenge is not None
        return self.challenge.model_copy(update={"consumed_at": NOW})


class FakeMFAService:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.passkeys = [PASSKEY]
        self.passkey_by_credential: UserPasskey | None = PASSKEY
        self.list_calls: list[int] = []
        self.lookup_calls: list[str] = []
        self.sign_count_calls: list[tuple[int, int]] = []

    def list_passkeys(self, user_id: int) -> list[UserPasskey]:
        self.list_calls.append(user_id)
        return self.passkeys

    def get_passkey_by_credential_id(self, credential_id: str) -> UserPasskey | None:
        self.lookup_calls.append(credential_id)
        return self.passkey_by_credential

    def update_passkey_sign_count(self, passkey_id: int, sign_count: int) -> None:
        self.events.append("mfa.update_sign_count")
        self.sign_count_calls.append((passkey_id, sign_count))


class FakeUserService:
    def __init__(self) -> None:
        self.user: User | None = USER
        self.calls: list[int] = []

    def get_by_id(self, user_id: int) -> User | None:
        self.calls.append(user_id)
        return self.user if self.user is not None and self.user.id == user_id else None


class FakeLoginService:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[dict[str, Any]] = []

    def complete_login(self, **kwargs: Any) -> FakeLoginResult:
        self.events.append("login.issue_key")
        self.calls.append(kwargs)
        return FakeLoginResult()


class FakeAuditService:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def safe_log_for(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


class FakeRateLimitService:
    def __init__(self) -> None:
        self.reservations = 0

    def reserve(self, **_kwargs: Any) -> bool:
        self.reservations += 1
        return self.reservations <= 5

    def clear(self, **_kwargs: str) -> None:
        self.reservations = 0


class DeterministicWebAuthn:
    def __init__(self) -> None:
        self.generate_calls: list[dict[str, Any]] = []
        self.options_calls: list[Any] = []
        self.verify_calls: list[dict[str, Any]] = []
        self.verification_error: Exception | None = None
        self.new_sign_count = 8

    def generate_authentication_options(self, **kwargs: Any) -> Any:
        self.generate_calls.append(kwargs)
        return SimpleNamespace(challenge=SERVER_CHALLENGE)

    def options_to_json(self, options: Any) -> str:
        self.options_calls.append(options)
        return json.dumps(OPTIONS_PAYLOAD)

    def base64url_to_bytes(self, value: str) -> bytes:
        values = {
            CREDENTIAL_ID: b"credential-id",
            PUBLIC_KEY: b"public-key",
        }
        return values[value]

    def verify_authentication_response(self, **kwargs: Any) -> Any:
        self.verify_calls.append(kwargs)
        if self.verification_error is not None:
            raise self.verification_error
        return SimpleNamespace(new_sign_count=self.new_sign_count)


@dataclass(slots=True)
class PasskeyHarness:
    client: TestClient
    app: Any
    challenge: FakeAuthChallengeService
    mfa: FakeMFAService
    user: FakeUserService
    login: FakeLoginService
    audit: FakeAuditService
    webauthn: DeterministicWebAuthn
    events: list[str]


@pytest.fixture()
def passkey_harness(monkeypatch: pytest.MonkeyPatch) -> PasskeyHarness:
    import rentivo.api.csrf as csrf

    monkeypatch.setattr(settings, "secret_key", "passkey-route-contract-signing-key")
    monkeypatch.setattr(settings, "access_cookie_name", "__Host-rentivo_access")
    monkeypatch.setattr(settings, "challenge_cookie_name", "__Host-rentivo_challenge")
    monkeypatch.setattr(settings, "csrf_cookie_name", "__Host-rentivo_csrf")
    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(settings, "api_key_login_ttl_seconds", 24 * 60 * 60)
    monkeypatch.setattr(settings, "webauthn_rp_id", "auth.rentivo.test")
    monkeypatch.setattr(settings, "webauthn_origin", "https://auth.rentivo.test")
    monkeypatch.setattr(csrf.secrets, "token_urlsafe", lambda _size: "deterministic-passkey-csrf")
    deterministic_webauthn = DeterministicWebAuthn()
    monkeypatch.setattr(
        webauthn,
        "generate_authentication_options",
        deterministic_webauthn.generate_authentication_options,
    )
    monkeypatch.setattr(webauthn, "options_to_json", deterministic_webauthn.options_to_json)
    monkeypatch.setattr(webauthn, "base64url_to_bytes", deterministic_webauthn.base64url_to_bytes)
    monkeypatch.setattr(
        webauthn,
        "verify_authentication_response",
        deterministic_webauthn.verify_authentication_response,
    )

    events: list[str] = []
    challenge = FakeAuthChallengeService(events)
    mfa = FakeMFAService(events)
    user = FakeUserService()
    login = FakeLoginService(events)
    audit = FakeAuditService()
    services = SimpleNamespace(
        auth_challenge=challenge,
        auth_rate_limit=FakeRateLimitService(),
        mfa=mfa,
        user=user,
        login=login,
        audit=audit,
    )
    app = create_app()
    app.dependency_overrides[get_services] = lambda: services
    return PasskeyHarness(
        client=TestClient(app),
        app=app,
        challenge=challenge,
        mfa=mfa,
        user=user,
        login=login,
        audit=audit,
        webauthn=deterministic_webauthn,
        events=events,
    )


def _cookie_header(nonce: str = CHALLENGE_NONCE) -> dict[str, str]:
    return {"Cookie": f"{settings.challenge_cookie_name}={nonce}"}


def _begin(harness: PasskeyHarness, *, challenge_id: str = CHALLENGE_ID, nonce: str = CHALLENGE_NONCE):
    return harness.client.post(
        "/api/v1/auth/mfa/passkeys/begin",
        json={"challenge_id": challenge_id},
        headers=_cookie_header(nonce),
    )


def _complete(
    harness: PasskeyHarness,
    *,
    challenge_id: str = CHALLENGE_ID,
    nonce: str = CHALLENGE_NONCE,
    assertion: dict[str, Any] = ASSERTION,
):
    return harness.client.post(
        "/api/v1/auth/mfa/passkeys/complete",
        json={"challenge_id": challenge_id, "credential": assertion},
        headers=_cookie_header(nonce),
    )


def _cookie_line(response: Any, name: str) -> str:
    lines = [value for value in response.headers.get_list("set-cookie") if value.startswith(f"{name}=")]
    assert len(lines) == 1
    return lines[0]


def _assert_success_cookies(response: Any) -> None:
    access = _cookie_line(response, settings.access_cookie_name)
    csrf = _cookie_line(response, settings.csrf_cookie_name)
    challenge = _cookie_line(response, settings.challenge_cookie_name)
    assert response.cookies[settings.access_cookie_name] == ACCESS_SECRET
    assert response.cookies[settings.csrf_cookie_name].split(".", 1)[0] == "deterministic-passkey-csrf"
    assert "Max-Age=86400" in access
    assert "; Secure" in access and "; HttpOnly" in access and "; SameSite=lax" in access
    assert "; Secure" in csrf and "; HttpOnly" not in csrf and "; SameSite=lax" in csrf
    assert challenge.startswith((f"{settings.challenge_cookie_name}=;", f'{settings.challenge_cookie_name}="";'))
    assert "Max-Age=0" in challenge
    assert "; Secure" in challenge and "; HttpOnly" in challenge and "; SameSite=lax" in challenge


def test_passkey_begin_persists_generated_server_challenge_conditionally(
    passkey_harness: PasskeyHarness,
) -> None:
    passkey_harness.challenge.challenge = _challenge(webauthn_challenge=None)

    response = _begin(passkey_harness)

    assert response.status_code == 200
    assert response.json() == OPTIONS_PAYLOAD
    assert CHALLENGE_NONCE not in response.text
    assert passkey_harness.mfa.list_calls == [USER.id]
    assert len(passkey_harness.webauthn.generate_calls) == 1
    generate_call = passkey_harness.webauthn.generate_calls[0]
    assert generate_call["rp_id"] == "auth.rentivo.test"
    assert [descriptor.id for descriptor in generate_call["allow_credentials"]] == [b"credential-id"]
    assert passkey_harness.challenge.webauthn_calls == [(CHALLENGE_ID, CHALLENGE_NONCE, "login", SERVER_CHALLENGE)]
    assert passkey_harness.challenge.challenge is not None
    assert passkey_harness.challenge.challenge.webauthn_challenge == SERVER_CHALLENGE


def test_passkey_begin_does_not_return_options_when_conditional_persistence_loses_race(
    passkey_harness: PasskeyHarness,
) -> None:
    passkey_harness.challenge.challenge = _challenge(webauthn_challenge=None)
    passkey_harness.challenge.allow_webauthn_update = False

    response = _begin(passkey_harness)

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_or_expired_challenge"
    assert passkey_harness.challenge.webauthn_calls == [(CHALLENGE_ID, CHALLENGE_NONCE, "login", SERVER_CHALLENGE)]
    assert CHALLENGE_NONCE not in response.text
    assert passkey_harness.login.calls == []


@pytest.mark.parametrize(
    "challenge",
    [
        _challenge(phase="oauth", webauthn_challenge=None),
        _challenge(methods=("totp", "recovery"), webauthn_challenge=None),
    ],
)
def test_passkey_begin_enforces_login_phase_and_allowed_method(
    passkey_harness: PasskeyHarness,
    challenge: AuthChallenge,
) -> None:
    passkey_harness.challenge.challenge = challenge

    response = _begin(passkey_harness)

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_or_expired_challenge"
    assert passkey_harness.challenge.webauthn_calls == []
    assert passkey_harness.login.calls == []


def test_passkey_complete_validates_server_values_then_consumes_before_one_login_key(
    passkey_harness: PasskeyHarness,
) -> None:
    response = _complete(passkey_harness)

    assert response.status_code == 200
    assert response.json()["status"] == "authenticated"
    assert response.json()["bootstrap"]["user"] == BOOTSTRAP["user"]
    assert ACCESS_SECRET not in response.text
    assert CHALLENGE_NONCE not in response.text
    assert passkey_harness.challenge.get_valid_calls == [(CHALLENGE_ID, CHALLENGE_NONCE, "login", "passkey")]
    assert passkey_harness.mfa.lookup_calls == [CREDENTIAL_ID]
    assert len(passkey_harness.webauthn.verify_calls) == 1
    verify_call = passkey_harness.webauthn.verify_calls[0]
    assert verify_call == {
        "credential": ASSERTION,
        "expected_challenge": SERVER_CHALLENGE,
        "expected_rp_id": "auth.rentivo.test",
        "expected_origin": "https://auth.rentivo.test",
        "credential_public_key": b"public-key",
        "credential_current_sign_count": PASSKEY.sign_count,
    }
    assert passkey_harness.challenge.consume_calls == [(CHALLENGE_ID, CHALLENGE_NONCE, "login", "passkey")]
    assert passkey_harness.events == ["challenge.consume", "mfa.update_sign_count", "login.issue_key"]
    assert passkey_harness.mfa.sign_count_calls == [(PASSKEY.id, 8)]
    assert len(passkey_harness.login.calls) == 1
    login_call = passkey_harness.login.calls[0]
    assert login_call["user"] == USER
    assert login_call["via"] == "passkey"
    assert login_call["audit_metadata"] == {"mfa": True, "method": "passkey"}
    assert [args[1] for args, _kwargs in passkey_harness.audit.calls] == [AuditEventType.MFA_PASSKEY_USED]
    assert passkey_harness.audit.calls[0][1]["metadata"] == {
        "ip": "testclient",
        "passkey_uuid": PASSKEY.uuid,
    }
    _assert_success_cookies(response)
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("state", ["missing", "expired", "replayed"])
def test_passkey_complete_rejects_missing_expired_and_replayed_challenges_before_verification(
    passkey_harness: PasskeyHarness,
    state: str,
) -> None:
    if state == "missing":
        passkey_harness.challenge.challenge = None
    elif state == "expired":
        passkey_harness.challenge.challenge = _challenge().model_copy(update={"expires_at": NOW})
    else:
        passkey_harness.challenge.consumed = True

    response = _complete(passkey_harness)

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_or_expired_challenge"
    assert response.json()["detail"] == "Desafio de autenticação inválido ou expirado."
    assert passkey_harness.webauthn.verify_calls == []
    assert passkey_harness.challenge.consume_calls == []
    assert passkey_harness.login.calls == []


def test_passkey_complete_requires_server_side_challenge_bytes(passkey_harness: PasskeyHarness) -> None:
    passkey_harness.challenge.challenge = _challenge(webauthn_challenge=None)

    response = _complete(passkey_harness)

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_or_expired_challenge"
    assert passkey_harness.webauthn.verify_calls == []
    assert passkey_harness.challenge.consume_calls == []
    assert passkey_harness.login.calls == []


def test_passkey_complete_rejects_a_user_deleted_after_challenge_issuance(
    passkey_harness: PasskeyHarness,
) -> None:
    passkey_harness.user.user = None

    response = _complete(passkey_harness)

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_or_expired_challenge"
    assert passkey_harness.webauthn.verify_calls == []
    assert passkey_harness.challenge.consume_calls == []
    assert passkey_harness.login.calls == []


def test_passkey_complete_binds_public_id_to_nonce_cookie(passkey_harness: PasskeyHarness) -> None:
    response = _complete(passkey_harness, nonce="nonce-from-another-browser")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_or_expired_challenge"
    assert passkey_harness.challenge.get_valid_calls == [
        (CHALLENGE_ID, "nonce-from-another-browser", "login", "passkey")
    ]
    assert passkey_harness.webauthn.verify_calls == []
    assert passkey_harness.login.calls == []


def test_passkey_complete_rejects_credential_owned_by_another_user(passkey_harness: PasskeyHarness) -> None:
    passkey_harness.mfa.passkey_by_credential = PASSKEY.model_copy(update={"user_id": OTHER_USER.id})

    response = _complete(passkey_harness)

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_passkey"
    assert OTHER_USER.email not in response.text
    assert passkey_harness.webauthn.verify_calls == []
    assert passkey_harness.challenge.consume_calls == []
    assert passkey_harness.login.calls == []


@pytest.mark.parametrize(
    "failure",
    [
        "challenge mismatch",
        "RP ID mismatch",
        "origin mismatch",
        "sign count did not increase",
    ],
)
def test_passkey_library_validation_failures_count_and_audit_without_consuming(
    passkey_harness: PasskeyHarness,
    failure: str,
) -> None:
    passkey_harness.webauthn.verification_error = ValueError(failure)

    response = _complete(passkey_harness)

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_passkey"
    assert failure not in response.text
    assert passkey_harness.challenge.failure_calls == [(CHALLENGE_ID, CHALLENGE_NONCE, "login", "passkey")]
    assert [args[1] for args, _kwargs in passkey_harness.audit.calls] == [AuditEventType.MFA_VERIFY_FAILED]
    assert passkey_harness.audit.calls[0][1]["metadata"] == {"ip": "testclient", "method": "passkey"}
    assert passkey_harness.challenge.consume_calls == []
    assert passkey_harness.mfa.sign_count_calls == []
    assert passkey_harness.login.calls == []


def test_atomic_consume_loss_after_valid_passkey_cannot_update_counter_or_issue_key(
    passkey_harness: PasskeyHarness,
) -> None:
    passkey_harness.challenge.allow_consume = False

    response = _complete(passkey_harness)

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_or_expired_challenge"
    assert len(passkey_harness.webauthn.verify_calls) == 1
    assert passkey_harness.events == ["challenge.consume"]
    assert passkey_harness.mfa.sign_count_calls == []
    assert passkey_harness.login.calls == []
    assert passkey_harness.audit.calls == []
    assert settings.access_cookie_name not in response.cookies


def test_replayed_passkey_completion_cannot_issue_a_second_login_key(
    passkey_harness: PasskeyHarness,
) -> None:
    first = _complete(passkey_harness)
    second = _complete(passkey_harness)

    assert first.status_code == 200
    assert second.status_code == 401
    assert second.json()["code"] == "invalid_or_expired_challenge"
    assert len(passkey_harness.webauthn.verify_calls) == 1
    assert len(passkey_harness.challenge.consume_calls) == 1
    assert len(passkey_harness.mfa.sign_count_calls) == 1
    assert len(passkey_harness.login.calls) == 1


def test_passkey_openapi_exposes_begin_and_complete_json_contracts(passkey_harness: PasskeyHarness) -> None:
    schema = passkey_harness.app.openapi()

    for operation_name in ("begin", "complete"):
        operation = schema["paths"][f"/api/v1/auth/mfa/passkeys/{operation_name}"]["post"]
        assert "auth" in operation["tags"]
        assert "application/json" in operation["requestBody"]["content"]
        assert {"200", "401", "422"}.issubset(operation["responses"])
