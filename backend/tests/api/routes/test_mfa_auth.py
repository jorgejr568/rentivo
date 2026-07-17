from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from rentivo.api.app import create_app
from rentivo.api.dependencies import get_services
from rentivo.constants.api_scopes import ALL_FIRST_PARTY_SCOPES
from rentivo.models.api_key import APIKey
from rentivo.models.audit_log import AuditEventType
from rentivo.models.auth_challenge import AuthChallenge
from rentivo.models.user import User
from rentivo.settings import settings

CHALLENGE_ID = "01K0MFAAUTHCHALLENGE0000000"
CHALLENGE_NONCE = "mfa-challenge-cookie-nonce"
FRESH_CHALLENGE_ID = "01K0MFAAUTHCHALLENGE0000001"
FRESH_CHALLENGE_NONCE = "fresh-mfa-challenge-cookie-nonce"
ACCESS_SECRET = f"rntv-v1-{'M' * 43}"
NOW = datetime(2026, 7, 17, 12, tzinfo=UTC)

USER = User(id=7, email="mfa-user@example.com")
OTHER_USER = User(id=8, email="other-mfa-user@example.com")
LOGIN_KEY = APIKey(
    id=11,
    uuid="mfa-login-key-uuid",
    user_id=USER.id,
    name="Web login",
    secret_hash=b"m" * 32,
    key_start="MMMM",
    key_end="MM",
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


def _challenge(*, phase: str = "login", methods: tuple[str, ...] = ("totp", "recovery", "passkey")):
    return AuthChallenge(
        id=3,
        uuid=CHALLENGE_ID,
        user_id=USER.id,
        phase=phase,
        nonce_hash=b"not-used-by-route-contract-tests",
        allowed_methods=methods,
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
        self.nonce = CHALLENGE_NONCE
        self.allow_consume = True
        self.consumed = False
        self.get_valid_calls: list[tuple[str, str, str, str | None]] = []
        self.failure_calls: list[tuple[str, str, str, str | None]] = []
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
            and nonce == self.nonce
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
    def __init__(self) -> None:
        self.totp_result = True
        self.recovery_result = True
        self.totp_calls: list[tuple[int, str]] = []
        self.recovery_calls: list[tuple[int, str]] = []

    def verify_totp(self, user_id: int, code: str) -> bool:
        self.totp_calls.append((user_id, code))
        return self.totp_result

    def verify_recovery_code(self, user_id: int, code: str) -> bool:
        self.recovery_calls.append((user_id, code))
        return self.recovery_result


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
        self.reservations: dict[tuple[str, str], int] = {}
        self.reserve_calls: list[dict[str, Any]] = []
        self.clear_calls: list[dict[str, str]] = []

    def reserve(self, **kwargs: Any) -> bool:
        self.reserve_calls.append(kwargs)
        key = (kwargs["action"], kwargs["identity"])
        self.reservations[key] = self.reservations.get(key, 0) + 1
        return self.reservations[key] <= kwargs["limit"]

    def clear(self, **kwargs: str) -> None:
        self.clear_calls.append(kwargs)
        self.reservations.pop((kwargs["action"], kwargs["identity"]), None)


@dataclass(slots=True)
class MFAHarness:
    client: TestClient
    app: Any
    challenge: FakeAuthChallengeService
    mfa: FakeMFAService
    user: FakeUserService
    login: FakeLoginService
    audit: FakeAuditService
    rate_limit: FakeRateLimitService
    events: list[str]


@pytest.fixture()
def mfa_harness(monkeypatch: pytest.MonkeyPatch) -> MFAHarness:
    import rentivo.api.csrf as csrf

    monkeypatch.setattr(settings, "secret_key", "mfa-route-contract-signing-key")
    monkeypatch.setattr(settings, "access_cookie_name", "__Host-rentivo_access")
    monkeypatch.setattr(settings, "challenge_cookie_name", "__Host-rentivo_challenge")
    monkeypatch.setattr(settings, "csrf_cookie_name", "__Host-rentivo_csrf")
    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(settings, "api_key_login_ttl_seconds", 24 * 60 * 60)
    monkeypatch.setattr(csrf.secrets, "token_urlsafe", lambda _size: "deterministic-mfa-csrf")
    events: list[str] = []
    challenge = FakeAuthChallengeService(events)
    mfa = FakeMFAService()
    user = FakeUserService()
    login = FakeLoginService(events)
    audit = FakeAuditService()
    rate_limit = FakeRateLimitService()
    services = SimpleNamespace(
        auth_challenge=challenge,
        auth_rate_limit=rate_limit,
        mfa=mfa,
        user=user,
        login=login,
        audit=audit,
    )
    app = create_app()
    app.dependency_overrides[get_services] = lambda: services
    return MFAHarness(
        client=TestClient(app),
        app=app,
        challenge=challenge,
        mfa=mfa,
        user=user,
        login=login,
        audit=audit,
        rate_limit=rate_limit,
        events=events,
    )


def _verify(
    harness: MFAHarness,
    method: str,
    *,
    nonce: str | None = CHALLENGE_NONCE,
    challenge_id: str = CHALLENGE_ID,
    code: str = "123456",
):
    headers = {} if nonce is None else {"Cookie": f"{settings.challenge_cookie_name}={nonce}"}
    return harness.client.post(
        f"/api/v1/auth/mfa/{method}/verify",
        json={"challenge_id": challenge_id, "code": code},
        headers=headers,
    )


def _cookie_line(response: Any, name: str) -> str:
    lines = [value for value in response.headers.get_list("set-cookie") if value.startswith(f"{name}=")]
    assert len(lines) == 1
    return lines[0]


def _assert_deleted_challenge_cookie(response: Any) -> None:
    line = _cookie_line(response, settings.challenge_cookie_name)
    assert line.startswith((f"{settings.challenge_cookie_name}=;", f'{settings.challenge_cookie_name}="";'))
    assert "Max-Age=0" in line
    assert "; Path=/" in line
    assert "; Secure" in line
    assert "; HttpOnly" in line
    assert "; SameSite=lax" in line


def _assert_login_cookies(response: Any) -> None:
    access = _cookie_line(response, settings.access_cookie_name)
    csrf = _cookie_line(response, settings.csrf_cookie_name)
    assert response.cookies[settings.access_cookie_name] == ACCESS_SECRET
    assert response.cookies[settings.csrf_cookie_name].split(".", 1)[0] == "deterministic-mfa-csrf"
    assert "Max-Age=86400" in access
    assert "; Secure" in access and "; HttpOnly" in access and "; SameSite=lax" in access
    assert "; Secure" in csrf and "; HttpOnly" not in csrf and "; SameSite=lax" in csrf


@pytest.mark.parametrize(
    ("method", "code", "expected_call"),
    [
        ("totp", "123456", "totp_calls"),
        ("recovery", "recovery-code", "recovery_calls"),
    ],
)
def test_code_mfa_consumes_login_challenge_before_issuing_exactly_one_login_key(
    mfa_harness: MFAHarness,
    method: str,
    code: str,
    expected_call: str,
) -> None:
    response = _verify(mfa_harness, method, code=code)

    assert response.status_code == 200
    assert response.json()["status"] == "authenticated"
    assert response.json()["bootstrap"]["user"] == BOOTSTRAP["user"]
    assert ACCESS_SECRET not in response.text
    assert CHALLENGE_NONCE not in response.text
    assert mfa_harness.events == ["challenge.consume", "login.issue_key"]
    assert len(mfa_harness.login.calls) == 1
    assert getattr(mfa_harness.mfa, expected_call) == [(USER.id, code)]
    assert mfa_harness.challenge.get_valid_calls == [(CHALLENGE_ID, CHALLENGE_NONCE, "login", method)]
    assert mfa_harness.challenge.consume_calls == [(CHALLENGE_ID, CHALLENGE_NONCE, "login", method)]
    login_call = mfa_harness.login.calls[0]
    assert login_call["user"] == USER
    assert login_call["via"] == "mfa"
    assert login_call["audit_metadata"] == {"mfa": True, "method": method}
    assert login_call["client_ip"] == "testclient"
    assert [args[1] for args, _kwargs in mfa_harness.audit.calls] == [AuditEventType.MFA_VERIFY_SUCCESS]
    assert mfa_harness.audit.calls[0][1]["metadata"] == {"ip": "testclient", "method": method}
    _assert_login_cookies(response)
    _assert_deleted_challenge_cookie(response)
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("method", ["totp", "recovery"])
def test_invalid_code_counts_challenge_failure_and_writes_failure_audit(
    mfa_harness: MFAHarness,
    method: str,
) -> None:
    if method == "totp":
        mfa_harness.mfa.totp_result = False
    else:
        mfa_harness.mfa.recovery_result = False

    response = _verify(mfa_harness, method, code="invalid-code")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "invalid_mfa_code"
    assert "invalid-code" not in response.text
    assert mfa_harness.challenge.failure_calls == [(CHALLENGE_ID, CHALLENGE_NONCE, "login", method)]
    assert mfa_harness.challenge.consume_calls == []
    assert mfa_harness.login.calls == []
    assert [args[1] for args, _kwargs in mfa_harness.audit.calls] == [AuditEventType.MFA_VERIFY_FAILED]
    assert mfa_harness.audit.calls[0][1]["metadata"] == {"ip": "testclient", "method": method}


def test_sixth_invalid_mfa_attempt_is_rate_limited_without_rechecking_the_code(
    mfa_harness: MFAHarness,
) -> None:
    mfa_harness.mfa.totp_result = False

    responses = [_verify(mfa_harness, "totp", code="000000") for _ in range(6)]

    assert [response.status_code for response in responses[:5]] == [401] * 5
    assert responses[5].status_code == 429
    assert responses[5].json()["code"] == "mfa_rate_limited"
    assert len(mfa_harness.mfa.totp_calls) == 5
    assert len(mfa_harness.challenge.failure_calls) == 5
    assert len(mfa_harness.audit.calls) == 5
    assert mfa_harness.login.calls == []


def test_fresh_challenge_does_not_reset_the_per_user_and_ip_mfa_rate_limit(
    mfa_harness: MFAHarness,
) -> None:
    mfa_harness.mfa.totp_result = False

    first_challenge = [_verify(mfa_harness, "totp", code="000000") for _ in range(5)]
    mfa_harness.challenge.challenge = _challenge().model_copy(update={"uuid": FRESH_CHALLENGE_ID})
    mfa_harness.challenge.nonce = FRESH_CHALLENGE_NONCE
    fresh_challenge = _verify(
        mfa_harness,
        "totp",
        challenge_id=FRESH_CHALLENGE_ID,
        nonce=FRESH_CHALLENGE_NONCE,
        code="000000",
    )

    assert [response.status_code for response in first_challenge] == [401] * 5
    assert fresh_challenge.status_code == 429
    assert fresh_challenge.json()["code"] == "mfa_rate_limited"
    assert len(mfa_harness.mfa.totp_calls) == 5
    assert [call["identity"] for call in mfa_harness.rate_limit.reserve_calls] == [f"{USER.id}:testclient"] * 6


def test_success_for_another_user_on_same_ip_does_not_clear_exhausted_bucket(
    mfa_harness: MFAHarness,
) -> None:
    mfa_harness.mfa.totp_result = False
    first_user = [_verify(mfa_harness, "totp", code="000000") for _ in range(5)]

    mfa_harness.challenge.challenge = _challenge().model_copy(
        update={"uuid": FRESH_CHALLENGE_ID, "user_id": OTHER_USER.id}
    )
    mfa_harness.challenge.nonce = FRESH_CHALLENGE_NONCE
    mfa_harness.user.user = OTHER_USER
    mfa_harness.mfa.totp_result = True
    other_user = _verify(
        mfa_harness,
        "totp",
        challenge_id=FRESH_CHALLENGE_ID,
        nonce=FRESH_CHALLENGE_NONCE,
    )

    final_challenge_id = "01K0MFAAUTHCHALLENGE0000002"
    final_nonce = "final-mfa-challenge-cookie-nonce"
    mfa_harness.challenge.challenge = _challenge().model_copy(update={"uuid": final_challenge_id})
    mfa_harness.challenge.nonce = final_nonce
    mfa_harness.challenge.consumed = False
    mfa_harness.user.user = USER
    mfa_harness.mfa.totp_result = False
    first_user_again = _verify(
        mfa_harness,
        "totp",
        challenge_id=final_challenge_id,
        nonce=final_nonce,
        code="000000",
    )

    assert [response.status_code for response in first_user] == [401] * 5
    assert other_user.status_code == 200
    assert first_user_again.status_code == 429
    assert mfa_harness.rate_limit.clear_calls == [{"action": "mfa_verify", "identity": f"{OTHER_USER.id}:testclient"}]
    assert [call["identity"] for call in mfa_harness.rate_limit.reserve_calls] == [
        *([f"{USER.id}:testclient"] * 5),
        f"{OTHER_USER.id}:testclient",
        f"{USER.id}:testclient",
    ]


def test_missing_challenge_cookie_is_rejected_before_service_lookup(mfa_harness: MFAHarness) -> None:
    response = _verify(mfa_harness, "totp", nonce=None)

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_or_expired_challenge"
    assert mfa_harness.challenge.get_valid_calls == []
    assert mfa_harness.mfa.totp_calls == []
    assert mfa_harness.login.calls == []


def test_public_challenge_id_is_bound_to_the_matching_nonce_cookie(mfa_harness: MFAHarness) -> None:
    response = _verify(mfa_harness, "recovery", nonce="nonce-from-another-browser")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_or_expired_challenge"
    assert mfa_harness.challenge.get_valid_calls == [(CHALLENGE_ID, "nonce-from-another-browser", "login", "recovery")]
    assert mfa_harness.mfa.recovery_calls == []
    assert mfa_harness.challenge.consume_calls == []
    assert mfa_harness.login.calls == []


@pytest.mark.parametrize("state", ["missing", "expired", "replayed"])
def test_missing_expired_and_replayed_challenges_share_one_non_disclosing_problem(
    mfa_harness: MFAHarness,
    state: str,
) -> None:
    if state == "missing":
        mfa_harness.challenge.challenge = None
    elif state == "expired":
        mfa_harness.challenge.challenge = _challenge().model_copy(update={"expires_at": NOW})
    else:
        mfa_harness.challenge.consumed = True

    response = _verify(mfa_harness, "totp")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_or_expired_challenge"
    assert response.json()["detail"] == "Desafio de autenticação inválido ou expirado."
    assert mfa_harness.mfa.totp_calls == []
    assert mfa_harness.challenge.consume_calls == []
    assert mfa_harness.login.calls == []


@pytest.mark.parametrize(
    "challenge",
    [
        _challenge(phase="oauth"),
        _challenge(methods=("recovery", "passkey")),
    ],
)
def test_totp_endpoint_rejects_wrong_phase_or_disallowed_method(
    mfa_harness: MFAHarness,
    challenge: AuthChallenge,
) -> None:
    mfa_harness.challenge.challenge = challenge

    response = _verify(mfa_harness, "totp")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_or_expired_challenge"
    assert mfa_harness.challenge.get_valid_calls == [(CHALLENGE_ID, CHALLENGE_NONCE, "login", "totp")]
    assert mfa_harness.mfa.totp_calls == []
    assert mfa_harness.login.calls == []


def test_atomic_consume_loss_cannot_issue_a_login_key_after_valid_code(mfa_harness: MFAHarness) -> None:
    mfa_harness.challenge.allow_consume = False

    response = _verify(mfa_harness, "totp")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_or_expired_challenge"
    assert mfa_harness.mfa.totp_calls == [(USER.id, "123456")]
    assert mfa_harness.events == ["challenge.consume"]
    assert mfa_harness.login.calls == []
    assert mfa_harness.audit.calls == []
    assert settings.access_cookie_name not in response.cookies
    assert settings.csrf_cookie_name not in response.cookies


def test_code_mfa_rejects_a_user_deleted_after_challenge_issuance(mfa_harness: MFAHarness) -> None:
    mfa_harness.user.user = None

    response = _verify(mfa_harness, "totp")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_or_expired_challenge"
    assert mfa_harness.mfa.totp_calls == []
    assert mfa_harness.challenge.consume_calls == []
    assert mfa_harness.login.calls == []


def test_mfa_openapi_exposes_json_verification_contracts(mfa_harness: MFAHarness) -> None:
    schema = mfa_harness.app.openapi()

    for method in ("totp", "recovery"):
        operation = schema["paths"][f"/api/v1/auth/mfa/{method}/verify"]["post"]
        assert "auth" in operation["tags"]
        assert "application/json" in operation["requestBody"]["content"]
        assert {"200", "401", "422", "429"}.issubset(operation["responses"])
