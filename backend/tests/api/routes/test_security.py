from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
import webauthn
from fastapi.testclient import TestClient
from starlette.responses import Response

from rentivo.api.app import create_app
from rentivo.api.csrf import CSRF_HEADER_NAME, issue_csrf_token
from rentivo.api.dependencies import get_services
from rentivo.api.principal import Principal
from rentivo.constants.api_scopes import ALL_FIRST_PARTY_SCOPES, APIScope
from rentivo.models.api_key import APIKey
from rentivo.models.audit_log import AuditEventType
from rentivo.models.auth_challenge import AuthChallenge
from rentivo.models.mfa import UserPasskey, UserTOTP
from rentivo.models.user import User
from rentivo.pix import validate_pix_key
from rentivo.services.audit_serializers import serialize_user
from rentivo.services.mfa_service import LastMFAFactorError
from rentivo.settings import settings

NOW = datetime(2026, 7, 17, 12, tzinfo=UTC)
LOGIN_SECRET = f"rntv-v1-{'L' * 43}"
SECOND_LOGIN_SECRET = f"rntv-v1-{'S' * 43}"
INTEGRATION_SECRET = f"rntv-v1-{'I' * 43}"
TOTP_SECRET = "JBSWY3DPEHPK3PXP"
RECOVERY_CODES = ["recover1", "recover2", "recover3"]
REGISTRATION_CHALLENGE_ID = "01K0SECURITYPASSKEY00000000"
REGISTRATION_NONCE = "registration-cookie-nonce"
SERVER_CHALLENGE = b"security-registration-challenge"
CREDENTIAL_ID = "bmV3LXBhc3NrZXktY3JlZGVudGlhbA"
PUBLIC_KEY = "bmV3LXBhc3NrZXktcHVibGljLWtleQ"

USER = User(
    id=7,
    email="security-user@example.com",
    password_hash="stored-password-hash-must-not-leak",
    pix_key="old@example.com",
    pix_merchant_name="Old Merchant",
    pix_merchant_city="Recife",
    created_at=NOW - timedelta(days=30),
)
OTHER_USER = User(id=8, email="other-user@example.com")


def _key(*, key_id: int, uuid: str, is_login_token: bool, scopes: frozenset[str]) -> APIKey:
    return APIKey(
        id=key_id,
        uuid=uuid,
        user_id=USER.id,
        name="Web login" if is_login_token else "Integration",
        secret_hash=bytes([key_id]) * 32,
        key_start="abcd",
        key_end="yz",
        is_login_token=is_login_token,
        scopes=scopes,
        expires_at=NOW + timedelta(days=1),
        created_at=NOW - timedelta(hours=1),
    )


LOGIN_KEY = _key(
    key_id=1,
    uuid="security-login-key",
    is_login_token=True,
    scopes=ALL_FIRST_PARTY_SCOPES,
)
SECOND_LOGIN_KEY = _key(
    key_id=2,
    uuid="security-second-login-key",
    is_login_token=True,
    scopes=ALL_FIRST_PARTY_SCOPES,
)
INTEGRATION_KEY = _key(
    key_id=3,
    uuid="security-integration-key",
    is_login_token=False,
    scopes=ALL_FIRST_PARTY_SCOPES,
)

EXISTING_PASSKEY = UserPasskey(
    id=21,
    uuid="existing-passkey-uuid",
    user_id=USER.id,
    credential_id="ZXhpc3RpbmctY3JlZGVudGlhbA",
    public_key="ZXhpc3RpbmctcHVibGljLWtleQ",
    sign_count=5,
    name="Notebook",
    transports='["internal"]',
    created_at=NOW - timedelta(days=10),
    last_used_at=NOW - timedelta(days=1),
)
OTHER_PASSKEY = UserPasskey(
    id=22,
    uuid="other-user-passkey-uuid",
    user_id=OTHER_USER.id,
    credential_id="b3RoZXItY3JlZGVudGlhbA",
    public_key="b3RoZXItcHVibGljLWtleQ",
    sign_count=1,
    name="Other user key",
    created_at=NOW - timedelta(days=2),
)

REGISTRATION_CREDENTIAL = {
    "id": CREDENTIAL_ID,
    "rawId": CREDENTIAL_ID,
    "type": "public-key",
    "response": {
        "attestationObject": "YXR0ZXN0YXRpb24",
        "clientDataJSON": "Y2xpZW50LWRhdGE",
    },
}
REGISTRATION_OPTIONS = {
    "challenge": "c2VjdXJpdHktcmVnaXN0cmF0aW9uLWNoYWxsZW5nZQ",
    "rp": {"id": "auth.rentivo.test", "name": "Rentivo Test"},
    "user": {
        "id": "Nw",
        "name": USER.email,
        "displayName": USER.email,
    },
    "excludeCredentials": [
        {"id": EXISTING_PASSKEY.credential_id, "type": "public-key"},
    ],
}


class FakeAPIKeyService:
    def __init__(self) -> None:
        self.keys = {
            LOGIN_SECRET: LOGIN_KEY,
            SECOND_LOGIN_SECRET: SECOND_LOGIN_KEY,
            INTEGRATION_SECRET: INTEGRATION_KEY,
        }
        self.revoke_other_calls: list[tuple[int, str]] = []
        self.revoke_all_calls: list[int] = []

    def authenticate(self, secret: str) -> APIKey | None:
        return self.keys.get(secret)

    def revoke_other_logins(self, user_id: int, current_key_uuid: str) -> int:
        self.revoke_other_calls.append((user_id, current_key_uuid))
        removed = 0
        for secret, key in tuple(self.keys.items()):
            if key.user_id == user_id and key.is_login_token and key.uuid != current_key_uuid:
                del self.keys[secret]
                removed += 1
        return removed

    def revoke_all_logins(self, user_id: int) -> int:
        self.revoke_all_calls.append(user_id)
        removed = 0
        for secret, key in tuple(self.keys.items()):
            if key.user_id == user_id and key.is_login_token:
                del self.keys[secret]
                removed += 1
        return removed


class FakeUserService:
    def __init__(self) -> None:
        self.user = USER
        self.current_password = "senha-atual"
        self.change_calls: list[tuple[int, str]] = []
        self.pix_calls: list[tuple[int, str, str, str]] = []

    def get_by_id(self, user_id: int) -> User | None:
        return self.user if user_id == self.user.id else None

    def authenticate(self, email: str, password: str) -> User | None:
        if email == self.user.email and password == self.current_password:
            return self.user
        return None

    def change_password(self, user_id: int, new_password: str) -> None:
        self.change_calls.append((user_id, new_password))
        self.current_password = new_password
        self.user = self.user.model_copy(update={"password_hash": "rotated-password-hash"})

    def update_pix(
        self,
        user_id: int,
        pix_key: str,
        pix_merchant_name: str,
        pix_merchant_city: str,
    ) -> User:
        normalized_key = validate_pix_key(pix_key) if pix_key.strip() else ""
        self.pix_calls.append((user_id, normalized_key, pix_merchant_name.strip(), pix_merchant_city.strip()))
        self.user = self.user.model_copy(
            update={
                "pix_key": normalized_key,
                "pix_merchant_name": pix_merchant_name.strip(),
                "pix_merchant_city": pix_merchant_city.strip(),
            }
        )
        return self.user


class FakeLoginService:
    def __init__(self, user: FakeUserService, api_key: FakeAPIKeyService) -> None:
        self.user = user
        self.api_key = api_key
        self.change_password_calls: list[dict[str, Any]] = []

    def change_password(
        self,
        *,
        principal: Principal,
        current_password: str,
        new_password: str,
    ) -> bool:
        self.change_password_calls.append(
            {
                "principal": principal,
                "current_password": current_password,
                "new_password": new_password,
            }
        )
        if self.user.authenticate(principal.user.email, current_password) is None:
            return False
        self.user.change_password(principal.user.id, new_password)
        self.api_key.revoke_other_logins(principal.user.id, principal.api_key.uuid)
        return True


class FakeMFAService:
    def __init__(self, api_key: FakeAPIKeyService) -> None:
        self.api_key = api_key
        self.totp: UserTOTP | None = UserTOTP(
            id=31,
            user_id=USER.id,
            secret=TOTP_SECRET,
            confirmed=True,
            created_at=NOW - timedelta(days=15),
            confirmed_at=NOW - timedelta(days=15),
        )
        self.recovery_codes = list(RECOVERY_CODES)
        self.passkeys = [EXISTING_PASSKEY, OTHER_PASSKEY]
        self.organization_enforced = True
        self.setup_required = False
        self.setup_calls: list[tuple[int, str]] = []
        self.confirm_calls: list[tuple[int, str, str]] = []
        self.disable_calls: list[int] = []
        self.regenerate_calls: list[int] = []
        self.register_calls: list[UserPasskey] = []
        self.register_login_tokens: list[str] = []
        self.delete_calls: list[tuple[str, int]] = []

    def get_totp(self, user_id: int) -> UserTOTP | None:
        return self.totp if user_id == USER.id else None

    def has_confirmed_totp(self, user_id: int) -> bool:
        totp = self.get_totp(user_id)
        return totp is not None and totp.confirmed

    def setup_totp(self, user_id: int, username: str) -> tuple[UserTOTP, str, str]:
        self.setup_calls.append((user_id, username))
        if self.has_confirmed_totp(user_id):
            raise ValueError("TOTP já está ativado")
        self.totp = UserTOTP(id=31, user_id=user_id, secret=TOTP_SECRET, confirmed=False, created_at=NOW)
        return self.totp, f"otpauth://totp/Rentivo:{username}?secret={TOTP_SECRET}", "cXItcG5n"

    def confirm_totp(self, user_id: int, code: str, current_login_token_uuid: str) -> list[str]:
        self.confirm_calls.append((user_id, code, current_login_token_uuid))
        if self.totp is None:
            raise ValueError("Nenhuma configuração TOTP em andamento")
        if code != "123456":
            raise ValueError("Código TOTP inválido")
        first_factor = not self.has_confirmed_totp(user_id) and not self.list_passkeys(user_id)
        self.totp = self.totp.model_copy(update={"confirmed": True, "confirmed_at": NOW})
        self.recovery_codes = list(RECOVERY_CODES)
        self.setup_required = False
        if first_factor:
            self.api_key.revoke_other_logins(user_id, current_login_token_uuid)
        return list(self.recovery_codes)

    def disable_totp(self, user_id: int) -> None:
        if self.totp is None:
            raise ValueError("TOTP não encontrado")
        if self.organization_enforced and not self.list_passkeys(user_id):
            raise LastMFAFactorError("MFA is required by an organization")
        self.disable_calls.append(user_id)
        self.totp = None
        self.recovery_codes = []
        self._revoke_logins(user_id)

    def regenerate_recovery_codes(self, user_id: int) -> list[str]:
        self.regenerate_calls.append(user_id)
        if not self.has_confirmed_totp(user_id):
            raise ValueError("TOTP não está ativado")
        self.recovery_codes = ["fresh001", "fresh002", "fresh003"]
        return list(self.recovery_codes)

    def count_unused_recovery_codes(self, user_id: int) -> int:
        return len(self.recovery_codes) if user_id == USER.id else 0

    def list_passkeys(self, user_id: int) -> list[UserPasskey]:
        return [passkey for passkey in self.passkeys if passkey.user_id == user_id]

    def register_passkey(self, passkey: UserPasskey, current_login_token_uuid: str) -> UserPasskey:
        first_factor = not self.has_confirmed_totp(passkey.user_id) and not self.list_passkeys(passkey.user_id)
        created = passkey.model_copy(
            update={
                "id": 23,
                "uuid": "registered-passkey-uuid",
                "created_at": NOW,
            }
        )
        self.passkeys.append(created)
        self.register_calls.append(created)
        self.register_login_tokens.append(current_login_token_uuid)
        self.setup_required = False
        if first_factor:
            self.api_key.revoke_other_logins(passkey.user_id, current_login_token_uuid)
        return created

    def delete_passkey(self, passkey_uuid: str, user_id: int) -> None:
        self.delete_calls.append((passkey_uuid, user_id))
        passkey = next((item for item in self.passkeys if item.uuid == passkey_uuid), None)
        if passkey is None or passkey.user_id != user_id:
            raise ValueError("Passkey não encontrada")
        other_passkeys = [item for item in self.list_passkeys(user_id) if item.id != passkey.id]
        if self.organization_enforced and not self.has_confirmed_totp(user_id) and not other_passkeys:
            raise LastMFAFactorError("MFA is required by an organization")
        self.passkeys.remove(passkey)
        self._revoke_logins(user_id)

    def _revoke_logins(self, user_id: int) -> None:
        for secret, key in tuple(self.api_key.keys.items()):
            if key.user_id == user_id and key.is_login_token:
                del self.api_key.keys[secret]

    def user_requires_mfa_setup(self, user_id: int) -> bool:
        return user_id == USER.id and self.setup_required

    def user_in_enforcing_org(self, user_id: int) -> bool:
        return user_id == USER.id and self.organization_enforced


def _registration_challenge() -> AuthChallenge:
    return AuthChallenge(
        id=41,
        uuid=REGISTRATION_CHALLENGE_ID,
        user_id=USER.id,
        phase="passkey_registration",
        nonce_hash=b"not-used-by-route-contract-test",
        allowed_methods=("passkey",),
        webauthn_challenge=SERVER_CHALLENGE,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )


class FakeAuthChallengeService:
    def __init__(self) -> None:
        self.challenge: AuthChallenge | None = _registration_challenge()
        self.consumed = False
        self.allow_consume = True
        self.issue_calls: list[dict[str, Any]] = []
        self.get_valid_calls: list[tuple[str, str, str, str | None]] = []
        self.consume_calls: list[tuple[str, str, str, str | None]] = []

    def issue(self, **kwargs: Any) -> Any:
        self.issue_calls.append(kwargs)
        self.challenge = _registration_challenge().model_copy(
            update={
                "user_id": kwargs["user_id"],
                "phase": kwargs["phase"],
                "allowed_methods": kwargs["allowed_methods"],
                "webauthn_challenge": kwargs.get("webauthn_challenge"),
            }
        )
        self.consumed = False
        return SimpleNamespace(challenge=self.challenge, nonce=REGISTRATION_NONCE)

    def get_valid(
        self,
        uuid: str,
        nonce: str,
        *,
        expected_phase: str,
        expected_method: str | None,
    ) -> AuthChallenge | None:
        self.get_valid_calls.append((uuid, nonce, expected_phase, expected_method))
        challenge = self.challenge
        if (
            challenge is None
            or self.consumed
            or uuid != challenge.uuid
            or nonce != REGISTRATION_NONCE
            or expected_phase != challenge.phase
            or (expected_method is not None and expected_method not in challenge.allowed_methods)
        ):
            return None
        return challenge

    def consume(
        self,
        uuid: str,
        nonce: str,
        *,
        expected_phase: str,
        expected_method: str | None,
    ) -> AuthChallenge | None:
        self.consume_calls.append((uuid, nonce, expected_phase, expected_method))
        challenge = self.get_valid(
            uuid,
            nonce,
            expected_phase=expected_phase,
            expected_method=expected_method,
        )
        if challenge is None or not self.allow_consume:
            return None
        self.consumed = True
        return challenge.model_copy(update={"consumed_at": NOW})


class FakeAuditService:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def safe_log_for(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


class FakeJobService:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.error: Exception | None = None

    def enqueue_for(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error


class DeterministicWebAuthn:
    def __init__(self) -> None:
        self.generate_calls: list[dict[str, Any]] = []
        self.verify_calls: list[dict[str, Any]] = []
        self.verification_error: Exception | None = None

    def generate_registration_options(self, **kwargs: Any) -> Any:
        self.generate_calls.append(kwargs)
        return SimpleNamespace(challenge=SERVER_CHALLENGE)

    def options_to_json(self, options: Any) -> str:
        assert options.challenge == SERVER_CHALLENGE
        return json.dumps(REGISTRATION_OPTIONS)

    @staticmethod
    def base64url_to_bytes(value: str) -> bytes:
        return value.encode()

    def verify_registration_response(self, **kwargs: Any) -> Any:
        self.verify_calls.append(kwargs)
        if self.verification_error is not None:
            raise self.verification_error
        return SimpleNamespace(
            credential_id=b"new-passkey-credential",
            credential_public_key=b"new-passkey-public-key",
            sign_count=0,
        )


@dataclass(slots=True)
class SecurityHarness:
    client: TestClient
    app: Any
    api_key: FakeAPIKeyService
    user: FakeUserService
    login: FakeLoginService
    mfa: FakeMFAService
    challenge: FakeAuthChallengeService
    audit: FakeAuditService
    job: FakeJobService
    webauthn: DeterministicWebAuthn

    def request(
        self,
        method: str,
        path: str,
        *,
        secret: str = LOGIN_SECRET,
        bearer: bool = False,
        csrf: bool = True,
        challenge_nonce: str | None = None,
        **kwargs: Any,
    ) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        key = {
            LOGIN_SECRET: LOGIN_KEY,
            SECOND_LOGIN_SECRET: SECOND_LOGIN_KEY,
            INTEGRATION_SECRET: INTEGRATION_KEY,
        }[secret]
        if bearer:
            headers["Authorization"] = f"Bearer {secret}"
        else:
            token = _csrf_token_for(key)
            cookies = [
                f"{settings.access_cookie_name}={secret}",
                f"{settings.csrf_cookie_name}={token}",
            ]
            if challenge_nonce is not None:
                cookies.append(f"{settings.challenge_cookie_name}={challenge_nonce}")
            headers["Cookie"] = "; ".join(cookies)
            if csrf:
                headers[CSRF_HEADER_NAME] = token
        return self.client.request(method, path, headers=headers, **kwargs)


def _csrf_token_for(key: APIKey) -> str:
    return issue_csrf_token(Response(), Principal(user=USER, api_key=key, source="web"))


@pytest.fixture()
def security_harness(monkeypatch: pytest.MonkeyPatch) -> SecurityHarness:
    import rentivo.api.csrf as csrf_module

    monkeypatch.setattr(settings, "secret_key", "security-route-contract-signing-key")
    monkeypatch.setattr(settings, "access_cookie_name", "__Host-rentivo_access")
    monkeypatch.setattr(settings, "challenge_cookie_name", "__Host-rentivo_challenge")
    monkeypatch.setattr(settings, "csrf_cookie_name", "__Host-rentivo_csrf")
    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(settings, "public_app_url", "https://app.rentivo.test")
    monkeypatch.setattr(settings, "webauthn_rp_id", "auth.rentivo.test")
    monkeypatch.setattr(settings, "webauthn_rp_name", "Rentivo Test")
    monkeypatch.setattr(settings, "webauthn_origin", "https://auth.rentivo.test")
    monkeypatch.setattr(csrf_module.secrets, "token_urlsafe", lambda _size: "deterministic-security-csrf")

    deterministic_webauthn = DeterministicWebAuthn()
    monkeypatch.setattr(
        webauthn,
        "generate_registration_options",
        deterministic_webauthn.generate_registration_options,
    )
    monkeypatch.setattr(webauthn, "options_to_json", deterministic_webauthn.options_to_json)
    monkeypatch.setattr(webauthn, "base64url_to_bytes", deterministic_webauthn.base64url_to_bytes)
    monkeypatch.setattr(
        webauthn,
        "verify_registration_response",
        deterministic_webauthn.verify_registration_response,
    )

    api_key = FakeAPIKeyService()
    user = FakeUserService()
    login = FakeLoginService(user, api_key)
    mfa = FakeMFAService(api_key)
    challenge = FakeAuthChallengeService()
    audit = FakeAuditService()
    job = FakeJobService()
    services = SimpleNamespace(
        api_key=api_key,
        user=user,
        login=login,
        mfa=mfa,
        auth_challenge=challenge,
        audit=audit,
        job=job,
    )
    app = create_app()
    app.dependency_overrides[get_services] = lambda: services
    return SecurityHarness(
        client=TestClient(app),
        app=app,
        api_key=api_key,
        user=user,
        login=login,
        mfa=mfa,
        challenge=challenge,
        audit=audit,
        job=job,
        webauthn=deterministic_webauthn,
    )


def _assert_problem(response: Any, *, status: int, code: str, detail: str) -> None:
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["code"] == code
    assert payload["detail"] == detail
    assert payload["type"] == f"https://rentivo.app/problems/{code}"
    assert payload["request_id"]


def _audit_events(harness: SecurityHarness) -> list[str]:
    return [args[1] for args, _kwargs in harness.audit.calls]


def _job_payloads(harness: SecurityHarness) -> list[dict[str, Any]]:
    return [args[2] for args, _kwargs in harness.job.calls]


def _assert_absent_from_side_effects(harness: SecurityHarness, *secrets: str) -> None:
    serialized = repr((harness.audit.calls, harness.job.calls))
    for secret in secrets:
        assert secret not in serialized


PRIVILEGED_REQUESTS = [
    ("GET", "/api/v1/security", None),
    ("POST", "/api/v1/security/pix", {"pix_key": "person@example.com"}),
    (
        "POST",
        "/api/v1/security/change-password",
        {
            "current_password": "senha-atual",
            "new_password": "nova-senha-segura",
            "confirm_password": "nova-senha-segura",
        },
    ),
    ("POST", "/api/v1/security/totp/setup", None),
    ("POST", "/api/v1/security/totp/confirm", {"code": "123456"}),
    ("POST", "/api/v1/security/totp/disable", {"password": "senha-atual"}),
    ("POST", "/api/v1/security/recovery-codes/regenerate", None),
    ("GET", "/api/v1/security/passkeys", None),
    ("POST", "/api/v1/security/passkeys/register/begin", None),
    (
        "POST",
        "/api/v1/security/passkeys/register/complete",
        {
            "challenge_id": REGISTRATION_CHALLENGE_ID,
            "credential": REGISTRATION_CREDENTIAL,
            "name": "Notebook novo",
        },
    ),
    ("DELETE", f"/api/v1/security/passkeys/{EXISTING_PASSKEY.uuid}", None),
]


@pytest.mark.parametrize(("method", "path", "payload"), PRIVILEGED_REQUESTS)
def test_integration_key_cannot_access_any_security_management_route(
    security_harness: SecurityHarness,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    response = security_harness.request(
        method,
        path,
        secret=INTEGRATION_SECRET,
        bearer=True,
        json=payload,
    )

    _assert_problem(
        response,
        status=403,
        code="login_token_required",
        detail="Esta operação requer login interativo.",
    )


@pytest.mark.parametrize(
    ("method", "path", "required_scope", "payload"),
    [
        (
            "POST",
            "/api/v1/security/change-password",
            APIScope.ACCOUNT_WRITE.value,
            {
                "current_password": "senha-atual",
                "new_password": "nova-senha-segura",
                "confirm_password": "nova-senha-segura",
            },
        ),
        (
            "POST",
            "/api/v1/security/pix",
            APIScope.ACCOUNT_WRITE.value,
            {"pix_key": "person@example.com", "pix_merchant_name": "Person", "pix_merchant_city": "Recife"},
        ),
        ("GET", "/api/v1/security", APIScope.SECURITY_MANAGE.value, None),
        ("POST", "/api/v1/security/passkeys/register/begin", APIScope.SECURITY_MANAGE.value, None),
    ],
)
def test_login_token_still_requires_the_endpoint_scope(
    security_harness: SecurityHarness,
    method: str,
    path: str,
    required_scope: str,
    payload: dict[str, Any] | None,
) -> None:
    security_harness.api_key.keys[LOGIN_SECRET] = LOGIN_KEY.model_copy(
        update={"scopes": ALL_FIRST_PARTY_SCOPES - {required_scope}}
    )

    response = security_harness.request(method, path, bearer=True, json=payload)

    _assert_problem(
        response,
        status=403,
        code="missing_scope",
        detail="A chave não possui o escopo necessário.",
    )


MUTATING_REQUESTS = [request for request in PRIVILEGED_REQUESTS if request[0] not in {"GET", "HEAD"}]


@pytest.mark.parametrize(("method", "path", "payload"), MUTATING_REQUESTS)
def test_cookie_authenticated_security_mutations_require_double_submit_csrf(
    security_harness: SecurityHarness,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    response = security_harness.request(method, path, csrf=False, json=payload)

    _assert_problem(
        response,
        status=403,
        code="csrf_failed",
        detail="Token CSRF inválido ou expirado.",
    )
    assert security_harness.user.change_calls == []
    assert security_harness.user.pix_calls == []
    assert security_harness.audit.calls == []
    assert security_harness.job.calls == []


def test_bearer_login_token_mutation_is_not_subject_to_csrf(security_harness: SecurityHarness) -> None:
    response = security_harness.request(
        "POST",
        "/api/v1/security/pix",
        bearer=True,
        json={
            "pix_key": " Person@Example.com ",
            "pix_merchant_name": " Person ",
            "pix_merchant_city": " Recife ",
        },
    )

    assert response.status_code == 200
    assert security_harness.user.pix_calls == [(USER.id, "person@example.com", "Person", "Recife")]


def test_security_summary_exposes_profile_and_mfa_state_without_stored_secrets(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request("GET", "/api/v1/security")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"] == {
        "email": USER.email,
        "pix_key": USER.pix_key,
        "pix_merchant_name": USER.pix_merchant_name,
        "pix_merchant_city": USER.pix_merchant_city,
    }
    assert payload["totp"] == {"enabled": True, "recovery_codes_remaining": len(RECOVERY_CODES)}
    assert payload["mfa"] == {"setup_required": False, "organization_enforced": True}
    assert payload["passkeys"] == [
        {
            "uuid": EXISTING_PASSKEY.uuid,
            "name": EXISTING_PASSKEY.name,
            "created_at": EXISTING_PASSKEY.created_at.isoformat().replace("+00:00", "Z"),
            "last_used_at": EXISTING_PASSKEY.last_used_at.isoformat().replace("+00:00", "Z"),
        }
    ]
    serialized = response.text
    for secret in (
        LOGIN_SECRET,
        USER.password_hash,
        TOTP_SECRET,
        EXISTING_PASSKEY.credential_id,
        EXISTING_PASSKEY.public_key,
    ):
        assert secret not in serialized
    assert "secret_hash" not in serialized
    assert "is_login_token" not in serialized


def test_security_summary_is_blocked_while_organization_mfa_setup_is_required(
    security_harness: SecurityHarness,
) -> None:
    security_harness.mfa.totp = None
    security_harness.mfa.passkeys = [OTHER_PASSKEY]
    security_harness.mfa.recovery_codes = []
    security_harness.mfa.setup_required = True

    response = security_harness.request("GET", "/api/v1/security")

    assert response.status_code == 403
    assert response.json()["code"] == "mfa_setup_required"


def test_pix_update_normalizes_profile_and_writes_redacted_audit_state(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request(
        "POST",
        "/api/v1/security/pix",
        json={
            "pix_key": " Merchant@Example.com ",
            "pix_merchant_name": " Merchant Name ",
            "pix_merchant_city": " Sao Paulo ",
        },
    )

    assert response.status_code == 200
    assert response.json()["profile"] == {
        "email": USER.email,
        "pix_key": "merchant@example.com",
        "pix_merchant_name": "Merchant Name",
        "pix_merchant_city": "Sao Paulo",
    }
    assert security_harness.user.pix_calls == [(USER.id, "merchant@example.com", "Merchant Name", "Sao Paulo")]
    assert _audit_events(security_harness) == [AuditEventType.USER_UPDATE]
    _args, kwargs = security_harness.audit.calls[0]
    assert kwargs["entity_type"] == "user"
    assert kwargs["entity_id"] == USER.id
    assert "password_hash" not in repr((kwargs["previous_state"], kwargs["new_state"]))
    assert "merchant@example.com" not in repr(kwargs["new_state"])
    assert LOGIN_SECRET not in repr(security_harness.audit.calls)


def test_invalid_pix_returns_stable_pt_br_field_problem_without_audit(
    security_harness: SecurityHarness,
) -> None:
    detail = "Chave PIX inválida. Use CPF, CNPJ, e-mail, telefone (+55...) ou chave aleatória (UUID)."

    response = security_harness.request(
        "POST",
        "/api/v1/security/pix",
        json={
            "pix_key": "not-a-pix-key",
            "pix_merchant_name": "Merchant",
            "pix_merchant_city": "Recife",
        },
    )

    _assert_problem(response, status=422, code="invalid_pix_key", detail=detail)
    assert response.json()["fields"] == {"pix_key": detail}
    assert security_harness.audit.calls == []


def test_password_change_keeps_current_session_and_revokes_only_other_login_tokens(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request(
        "POST",
        "/api/v1/security/change-password",
        json={
            "current_password": "senha-atual",
            "new_password": "nova-senha-segura",
            "confirm_password": "nova-senha-segura",
        },
    )

    assert response.status_code == 204
    assert response.headers["x-rentivo-analytics-event"] == "rentivo_password_changed"
    assert security_harness.user.change_calls == [(USER.id, "nova-senha-segura")]
    assert security_harness.api_key.revoke_other_calls == [(USER.id, LOGIN_KEY.uuid)]
    assert LOGIN_SECRET in security_harness.api_key.keys
    assert SECOND_LOGIN_SECRET not in security_harness.api_key.keys
    assert INTEGRATION_SECRET in security_harness.api_key.keys
    assert security_harness.request("GET", "/api/v1/security").status_code == 200
    assert (
        security_harness.request(
            "GET",
            "/api/v1/security",
            secret=SECOND_LOGIN_SECRET,
            bearer=True,
        ).status_code
        == 401
    )
    assert (
        security_harness.request(
            "GET",
            "/api/v1/security",
            secret=INTEGRATION_SECRET,
            bearer=True,
        ).status_code
        == 403
    )
    assert _audit_events(security_harness) == [AuditEventType.USER_CHANGE_PASSWORD]
    _args, audit_kwargs = security_harness.audit.calls[0]
    assert audit_kwargs["new_state"] == serialize_user(USER)
    assert USER.email not in repr(audit_kwargs["new_state"])
    assert [payload["event"] for payload in _job_payloads(security_harness)] == ["password_changed"]
    assert _job_payloads(security_harness)[0]["to_email"] == USER.email
    assert _job_payloads(security_harness)[0]["ctx"]["reset_url"] == ("https://app.rentivo.test/forgot-password")
    _assert_absent_from_side_effects(
        security_harness,
        LOGIN_SECRET,
        SECOND_LOGIN_SECRET,
        "senha-atual",
        "nova-senha-segura",
        USER.password_hash,
    )


def test_password_change_succeeds_when_notification_dispatch_fails(
    security_harness: SecurityHarness,
) -> None:
    security_harness.job.error = RuntimeError("queue unavailable")

    response = security_harness.request(
        "POST",
        "/api/v1/security/change-password",
        json={
            "current_password": "senha-atual",
            "new_password": "nova-senha-segura",
            "confirm_password": "nova-senha-segura",
        },
    )

    assert response.status_code == 204
    assert security_harness.user.change_calls == [(USER.id, "nova-senha-segura")]
    assert security_harness.api_key.revoke_other_calls == [(USER.id, LOGIN_KEY.uuid)]
    assert _audit_events(security_harness) == [AuditEventType.USER_CHANGE_PASSWORD]


@pytest.mark.parametrize(
    ("payload", "status", "code", "detail", "field"),
    [
        (
            {
                "current_password": "senha-incorreta",
                "new_password": "nova-senha-segura",
                "confirm_password": "nova-senha-segura",
            },
            400,
            "incorrect_current_password",
            "Senha atual incorreta.",
            None,
        ),
        (
            {
                "current_password": "senha-atual",
                "new_password": "nova-senha-segura",
                "confirm_password": "outra-senha",
            },
            422,
            "validation_error",
            "As senhas não coincidem.",
            "confirm_password",
        ),
    ],
)
def test_password_change_errors_preserve_pt_br_copy_and_have_no_side_effects(
    security_harness: SecurityHarness,
    payload: dict[str, str],
    status: int,
    code: str,
    detail: str,
    field: str | None,
) -> None:
    response = security_harness.request(
        "POST",
        "/api/v1/security/change-password",
        json=payload,
    )

    _assert_problem(response, status=status, code=code, detail=detail)
    if field is not None:
        assert response.json()["fields"] == {field: detail}
    assert security_harness.user.change_calls == []
    assert security_harness.api_key.revoke_other_calls == []
    assert security_harness.audit.calls == []
    assert security_harness.job.calls == []


def test_totp_setup_returns_only_deliberate_setup_material_with_no_store(
    security_harness: SecurityHarness,
) -> None:
    security_harness.mfa.totp = None
    security_harness.mfa.setup_required = True

    response = security_harness.request("POST", "/api/v1/security/totp/setup")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "secret": TOTP_SECRET,
        "provisioning_uri": f"otpauth://totp/Rentivo:{USER.email}?secret={TOTP_SECRET}",
        "qr_code_base64": "cXItcG5n",
    }
    assert security_harness.mfa.setup_calls == [(USER.id, USER.email)]
    assert LOGIN_SECRET not in response.text
    assert USER.password_hash not in response.text
    assert security_harness.audit.calls == []
    assert security_harness.job.calls == []


def test_totp_setup_rejects_an_already_enabled_authenticator(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request("POST", "/api/v1/security/totp/setup")

    _assert_problem(
        response,
        status=409,
        code="totp_already_enabled",
        detail="TOTP já está ativado",
    )


def test_totp_setup_get_is_not_an_operation(security_harness: SecurityHarness) -> None:
    security_harness.mfa.totp = None

    response = security_harness.request("GET", "/api/v1/security/totp/setup")

    assert response.status_code == 405
    assert security_harness.mfa.setup_calls == []


def test_totp_confirm_returns_recovery_codes_once_and_preserves_effects(
    security_harness: SecurityHarness,
) -> None:
    security_harness.mfa.totp = UserTOTP(id=31, user_id=USER.id, secret=TOTP_SECRET, confirmed=False)
    security_harness.mfa.recovery_codes = []
    security_harness.mfa.setup_required = True

    response = security_harness.request(
        "POST",
        "/api/v1/security/totp/confirm",
        json={"code": "123456"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-rentivo-analytics-event"] == "rentivo_mfa_enabled"
    assert response.headers["x-rentivo-analytics-method"] == "totp"
    assert response.json() == {"recovery_codes": RECOVERY_CODES}
    assert security_harness.mfa.confirm_calls == [(USER.id, "123456", LOGIN_KEY.uuid)]
    assert security_harness.mfa.setup_required is False
    assert _audit_events(security_harness) == [AuditEventType.MFA_TOTP_ENABLED]
    payloads = _job_payloads(security_harness)
    assert [payload["event"] for payload in payloads] == ["mfa_changed"]
    assert payloads[0]["ctx"]["change_label"] == "TOTP ativado"
    _assert_absent_from_side_effects(security_harness, LOGIN_SECRET, TOTP_SECRET, *RECOVERY_CODES)

    summary = security_harness.request("GET", "/api/v1/security")
    assert summary.status_code == 200
    assert summary.json()["totp"] == {
        "enabled": True,
        "recovery_codes_remaining": len(RECOVERY_CODES),
    }
    for recovery_code in RECOVERY_CODES:
        assert recovery_code not in summary.text


def test_first_totp_factor_revokes_other_logins_but_preserves_enrollment_session(
    security_harness: SecurityHarness,
) -> None:
    security_harness.mfa.totp = UserTOTP(id=31, user_id=USER.id, secret=TOTP_SECRET, confirmed=False)
    security_harness.mfa.passkeys = [OTHER_PASSKEY]
    security_harness.mfa.recovery_codes = []
    security_harness.mfa.setup_required = True

    response = security_harness.request(
        "POST",
        "/api/v1/security/totp/confirm",
        json={"code": "123456"},
    )

    assert response.status_code == 200
    assert security_harness.api_key.revoke_other_calls == [(USER.id, LOGIN_KEY.uuid)]
    assert LOGIN_SECRET in security_harness.api_key.keys
    assert SECOND_LOGIN_SECRET not in security_harness.api_key.keys
    assert INTEGRATION_SECRET in security_harness.api_key.keys
    assert security_harness.request("GET", "/api/v1/security").status_code == 200
    assert (
        security_harness.request(
            "GET",
            "/api/v1/security",
            secret=SECOND_LOGIN_SECRET,
            bearer=True,
        ).status_code
        == 401
    )


def test_totp_confirm_still_returns_one_time_codes_when_notification_dispatch_fails(
    security_harness: SecurityHarness,
) -> None:
    security_harness.mfa.totp = UserTOTP(id=31, user_id=USER.id, secret=TOTP_SECRET, confirmed=False)
    security_harness.mfa.recovery_codes = []
    security_harness.job.error = RuntimeError("queue unavailable")

    response = security_harness.request(
        "POST",
        "/api/v1/security/totp/confirm",
        json={"code": "123456"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"recovery_codes": RECOVERY_CODES}
    assert _audit_events(security_harness) == [AuditEventType.MFA_TOTP_ENABLED]


def test_totp_confirm_rejects_an_invalid_code_without_side_effects(
    security_harness: SecurityHarness,
) -> None:
    security_harness.mfa.totp = UserTOTP(id=31, user_id=USER.id, secret=TOTP_SECRET, confirmed=False)

    response = security_harness.request(
        "POST",
        "/api/v1/security/totp/confirm",
        json={"code": "000000"},
    )

    _assert_problem(response, status=400, code="invalid_totp_code", detail="Código TOTP inválido")
    assert security_harness.audit.calls == []
    assert security_harness.job.calls == []


def test_totp_disable_preserves_audit_analytics_and_notification_parity(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request(
        "POST",
        "/api/v1/security/totp/disable",
        json={"password": "senha-atual"},
    )

    assert response.status_code == 204
    assert response.headers["x-rentivo-analytics-event"] == "rentivo_mfa_disabled"
    assert security_harness.mfa.disable_calls == [USER.id]
    # Session revocation is committed by the same locked MFA-factor transaction.
    assert security_harness.api_key.revoke_all_calls == []
    assert LOGIN_SECRET not in security_harness.api_key.keys
    assert SECOND_LOGIN_SECRET not in security_harness.api_key.keys
    assert INTEGRATION_SECRET in security_harness.api_key.keys
    set_cookies = response.headers.get_list("set-cookie")
    assert any(line.startswith(f"{settings.access_cookie_name}=") and "Max-Age=0" in line for line in set_cookies)
    assert any(line.startswith(f"{settings.csrf_cookie_name}=") and "Max-Age=0" in line for line in set_cookies)
    assert _audit_events(security_harness) == [AuditEventType.MFA_TOTP_DISABLED]
    payloads = _job_payloads(security_harness)
    assert [payload["event"] for payload in payloads] == ["mfa_changed"]
    assert payloads[0]["ctx"]["change_label"] == "TOTP desativado"
    _assert_absent_from_side_effects(security_harness, LOGIN_SECRET, TOTP_SECRET, "senha-atual")


def test_totp_disable_is_blocked_by_organization_policy_with_pt_br_problem(
    security_harness: SecurityHarness,
) -> None:
    security_harness.mfa.passkeys = [OTHER_PASSKEY]

    response = security_harness.request(
        "POST",
        "/api/v1/security/totp/disable",
        json={"password": "senha-atual"},
    )

    _assert_problem(
        response,
        status=409,
        code="mfa_required_by_organization",
        detail="Você não pode desativar MFA enquanto pertence a uma organização que exige MFA.",
    )
    assert security_harness.mfa.disable_calls == []
    assert security_harness.audit.calls == []
    assert security_harness.job.calls == []


def test_totp_disable_is_allowed_when_another_factor_satisfies_organization_policy(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request(
        "POST",
        "/api/v1/security/totp/disable",
        json={"password": "senha-atual"},
    )

    assert response.status_code == 204
    assert security_harness.mfa.disable_calls == [USER.id]
    assert security_harness.mfa.list_passkeys(USER.id) == [EXISTING_PASSKEY]


def test_totp_disable_rejects_an_incorrect_password_before_policy_checks(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request(
        "POST",
        "/api/v1/security/totp/disable",
        json={"password": "senha-incorreta"},
    )

    _assert_problem(response, status=400, code="incorrect_password", detail="Senha incorreta.")
    assert security_harness.mfa.disable_calls == []
    assert security_harness.audit.calls == []


def test_totp_disable_reports_when_totp_is_not_enabled(
    security_harness: SecurityHarness,
) -> None:
    security_harness.mfa.totp = None

    response = security_harness.request(
        "POST",
        "/api/v1/security/totp/disable",
        json={"password": "senha-atual"},
    )

    _assert_problem(response, status=409, code="totp_not_enabled", detail="TOTP não está ativado.")
    assert security_harness.audit.calls == []


def test_recovery_code_regeneration_is_one_time_no_store_and_audited(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request(
        "POST",
        "/api/v1/security/recovery-codes/regenerate",
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-rentivo-analytics-event"] == "rentivo_recovery_codes_regenerated"
    assert response.json() == {"recovery_codes": ["fresh001", "fresh002", "fresh003"]}
    assert security_harness.mfa.regenerate_calls == [USER.id]
    assert _audit_events(security_harness) == [AuditEventType.MFA_RECOVERY_REGENERATED]
    assert security_harness.job.calls == []
    _assert_absent_from_side_effects(security_harness, LOGIN_SECRET, "fresh001", "fresh002", "fresh003")


def test_recovery_code_regeneration_without_totp_returns_pt_br_conflict(
    security_harness: SecurityHarness,
) -> None:
    security_harness.mfa.totp = None

    response = security_harness.request(
        "POST",
        "/api/v1/security/recovery-codes/regenerate",
    )

    _assert_problem(
        response,
        status=409,
        code="totp_required",
        detail="TOTP não está ativado.",
    )
    assert security_harness.audit.calls == []


def test_passkey_registration_begin_uses_server_state_and_excludes_existing_credentials(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request(
        "POST",
        "/api/v1/security/passkeys/register/begin",
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "challenge_id": REGISTRATION_CHALLENGE_ID,
        "options": REGISTRATION_OPTIONS,
    }
    assert len(security_harness.webauthn.generate_calls) == 1
    generate_call = security_harness.webauthn.generate_calls[0]
    assert generate_call["rp_id"] == "auth.rentivo.test"
    assert len(generate_call["user_id"]) == 32
    assert generate_call["user_id"] != str(USER.id).encode()
    assert [descriptor.id for descriptor in generate_call["exclude_credentials"]] == [
        EXISTING_PASSKEY.credential_id.encode()
    ]
    assert security_harness.challenge.issue_calls == [
        {
            "user_id": USER.id,
            "phase": "passkey_registration",
            "allowed_methods": ("passkey",),
            "webauthn_challenge": SERVER_CHALLENGE,
        }
    ]
    challenge_cookie = response.headers.get_list("set-cookie")
    assert any(
        line.startswith(f"{settings.challenge_cookie_name}={REGISTRATION_NONCE}")
        and "; Secure" in line
        and "; HttpOnly" in line
        and "; SameSite=lax" in line
        for line in challenge_cookie
    )
    assert REGISTRATION_NONCE not in response.text
    assert LOGIN_SECRET not in response.text


def test_passkey_registration_begin_is_allowed_during_enforced_mfa_setup(
    security_harness: SecurityHarness,
) -> None:
    security_harness.mfa.totp = None
    security_harness.mfa.passkeys = [OTHER_PASSKEY]
    security_harness.mfa.setup_required = True

    response = security_harness.request(
        "POST",
        "/api/v1/security/passkeys/register/begin",
    )

    assert response.status_code == 200
    assert security_harness.challenge.issue_calls[0]["user_id"] == USER.id


def test_passkey_registration_user_handle_is_stable_and_opaque(
    security_harness: SecurityHarness,
) -> None:
    first = security_harness.request("POST", "/api/v1/security/passkeys/register/begin")
    second = security_harness.request("POST", "/api/v1/security/passkeys/register/begin")

    assert first.status_code == second.status_code == 200
    first_handle, second_handle = [call["user_id"] for call in security_harness.webauthn.generate_calls]
    assert first_handle == second_handle
    assert len(first_handle) == 32
    assert str(USER.id).encode() not in first_handle


def test_passkey_registration_complete_returns_metadata_and_preserves_effects(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request(
        "POST",
        "/api/v1/security/passkeys/register/complete",
        challenge_nonce=REGISTRATION_NONCE,
        json={
            "challenge_id": REGISTRATION_CHALLENGE_ID,
            "credential": REGISTRATION_CREDENTIAL,
            "name": "Notebook novo",
        },
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-rentivo-analytics-event"] == "rentivo_passkey_added"
    assert response.json() == {
        "uuid": "registered-passkey-uuid",
        "name": "Notebook novo",
        "created_at": NOW.isoformat().replace("+00:00", "Z"),
        "last_used_at": None,
    }
    assert security_harness.challenge.get_valid_calls[0] == (
        REGISTRATION_CHALLENGE_ID,
        REGISTRATION_NONCE,
        "passkey_registration",
        "passkey",
    )
    assert security_harness.challenge.consume_calls == [
        (
            REGISTRATION_CHALLENGE_ID,
            REGISTRATION_NONCE,
            "passkey_registration",
            "passkey",
        )
    ]
    assert len(security_harness.webauthn.verify_calls) == 1
    verify_call = security_harness.webauthn.verify_calls[0]
    assert verify_call["expected_challenge"] == SERVER_CHALLENGE
    assert verify_call["expected_rp_id"] == "auth.rentivo.test"
    assert verify_call["expected_origin"] == "https://auth.rentivo.test"
    assert len(security_harness.mfa.register_calls) == 1
    assert _audit_events(security_harness) == [AuditEventType.MFA_PASSKEY_REGISTERED]
    assert _job_payloads(security_harness)[0]["event"] == "mfa_changed"
    assert _job_payloads(security_harness)[0]["ctx"]["change_label"] == "Passkey registrado"
    serialized = response.text
    for secret in (LOGIN_SECRET, REGISTRATION_NONCE, CREDENTIAL_ID, PUBLIC_KEY):
        assert secret not in serialized
    _assert_absent_from_side_effects(
        security_harness,
        LOGIN_SECRET,
        REGISTRATION_NONCE,
        CREDENTIAL_ID,
        PUBLIC_KEY,
    )


def test_passkey_registration_complete_is_allowed_during_enforced_mfa_setup(
    security_harness: SecurityHarness,
) -> None:
    security_harness.mfa.totp = None
    security_harness.mfa.passkeys = [OTHER_PASSKEY]
    security_harness.mfa.setup_required = True

    response = security_harness.request(
        "POST",
        "/api/v1/security/passkeys/register/complete",
        challenge_nonce=REGISTRATION_NONCE,
        json={
            "challenge_id": REGISTRATION_CHALLENGE_ID,
            "credential": REGISTRATION_CREDENTIAL,
            "name": "Primeira passkey",
        },
    )

    assert response.status_code == 200
    assert security_harness.mfa.setup_required is False
    assert security_harness.mfa.register_login_tokens == [LOGIN_KEY.uuid]
    assert security_harness.api_key.revoke_other_calls == [(USER.id, LOGIN_KEY.uuid)]
    assert LOGIN_SECRET in security_harness.api_key.keys
    assert SECOND_LOGIN_SECRET not in security_harness.api_key.keys
    assert INTEGRATION_SECRET in security_harness.api_key.keys


def test_passkey_registration_succeeds_when_notification_dispatch_fails(
    security_harness: SecurityHarness,
) -> None:
    security_harness.job.error = RuntimeError("queue unavailable")

    response = security_harness.request(
        "POST",
        "/api/v1/security/passkeys/register/complete",
        challenge_nonce=REGISTRATION_NONCE,
        json={
            "challenge_id": REGISTRATION_CHALLENGE_ID,
            "credential": REGISTRATION_CREDENTIAL,
            "name": "Notebook novo",
        },
    )

    assert response.status_code == 200
    assert response.json()["uuid"] == "registered-passkey-uuid"
    assert len(security_harness.mfa.register_calls) == 1
    assert _audit_events(security_harness) == [AuditEventType.MFA_PASSKEY_REGISTERED]


def test_passkey_registration_rejects_unknown_nested_credential_fields(
    security_harness: SecurityHarness,
) -> None:
    credential = json.loads(json.dumps(REGISTRATION_CREDENTIAL))
    credential["response"]["internalOnly"] = "must-not-pass-validation"

    response = security_harness.request(
        "POST",
        "/api/v1/security/passkeys/register/complete",
        challenge_nonce=REGISTRATION_NONCE,
        json={
            "challenge_id": REGISTRATION_CHALLENGE_ID,
            "credential": credential,
            "name": "Notebook novo",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert security_harness.webauthn.verify_calls == []
    assert security_harness.mfa.register_calls == []


def test_passkey_registration_complete_rejects_invalid_or_unbound_challenge(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request(
        "POST",
        "/api/v1/security/passkeys/register/complete",
        challenge_nonce="nonce-from-another-browser",
        json={
            "challenge_id": REGISTRATION_CHALLENGE_ID,
            "credential": REGISTRATION_CREDENTIAL,
            "name": "Notebook novo",
        },
    )

    _assert_problem(
        response,
        status=401,
        code="invalid_or_expired_challenge",
        detail="Desafio de autenticação inválido ou expirado.",
    )
    assert security_harness.webauthn.verify_calls == []
    assert security_harness.mfa.register_calls == []


def test_passkey_registration_complete_hides_webauthn_validation_failure(
    security_harness: SecurityHarness,
) -> None:
    security_harness.webauthn.verification_error = ValueError("origin mismatch secret detail")

    response = security_harness.request(
        "POST",
        "/api/v1/security/passkeys/register/complete",
        challenge_nonce=REGISTRATION_NONCE,
        json={
            "challenge_id": REGISTRATION_CHALLENGE_ID,
            "credential": REGISTRATION_CREDENTIAL,
            "name": "Notebook novo",
        },
    )

    _assert_problem(
        response,
        status=400,
        code="invalid_passkey_registration",
        detail="Falha na verificação da passkey.",
    )
    assert "origin mismatch" not in response.text
    assert security_harness.mfa.register_calls == []


def test_passkey_registration_rejects_a_blank_name_before_webauthn(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request(
        "POST",
        "/api/v1/security/passkeys/register/complete",
        challenge_nonce=REGISTRATION_NONCE,
        json={
            "challenge_id": REGISTRATION_CHALLENGE_ID,
            "credential": REGISTRATION_CREDENTIAL,
            "name": "   ",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert security_harness.webauthn.verify_calls == []
    assert security_harness.mfa.register_calls == []


def test_passkey_registration_consume_race_cannot_register_a_credential(
    security_harness: SecurityHarness,
) -> None:
    security_harness.challenge.allow_consume = False

    response = security_harness.request(
        "POST",
        "/api/v1/security/passkeys/register/complete",
        challenge_nonce=REGISTRATION_NONCE,
        json={
            "challenge_id": REGISTRATION_CHALLENGE_ID,
            "credential": REGISTRATION_CREDENTIAL,
            "name": "Notebook novo",
        },
    )

    _assert_problem(
        response,
        status=401,
        code="invalid_or_expired_challenge",
        detail="Desafio de autenticação inválido ou expirado.",
    )
    assert len(security_harness.webauthn.verify_calls) == 1
    assert security_harness.mfa.register_calls == []
    assert security_harness.audit.calls == []


def test_passkey_list_returns_only_owner_metadata_without_credential_material(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request("GET", "/api/v1/security/passkeys")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "uuid": EXISTING_PASSKEY.uuid,
                "name": EXISTING_PASSKEY.name,
                "created_at": EXISTING_PASSKEY.created_at.isoformat().replace("+00:00", "Z"),
                "last_used_at": EXISTING_PASSKEY.last_used_at.isoformat().replace("+00:00", "Z"),
            }
        ]
    }
    for secret in (
        LOGIN_SECRET,
        EXISTING_PASSKEY.credential_id,
        EXISTING_PASSKEY.public_key,
        OTHER_PASSKEY.uuid,
    ):
        assert secret not in response.text
    assert "sign_count" not in response.text
    assert "transports" not in response.text


def test_passkey_delete_is_owner_scoped_audited_notified_and_analysed(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request(
        "DELETE",
        f"/api/v1/security/passkeys/{EXISTING_PASSKEY.uuid}",
    )

    assert response.status_code == 204
    assert response.headers["x-rentivo-analytics-event"] == "rentivo_passkey_removed"
    assert security_harness.mfa.delete_calls == [(EXISTING_PASSKEY.uuid, USER.id)]
    assert security_harness.mfa.list_passkeys(USER.id) == []
    # Session revocation is committed by the same locked MFA-factor transaction.
    assert security_harness.api_key.revoke_all_calls == []
    assert LOGIN_SECRET not in security_harness.api_key.keys
    assert SECOND_LOGIN_SECRET not in security_harness.api_key.keys
    assert INTEGRATION_SECRET in security_harness.api_key.keys
    set_cookies = response.headers.get_list("set-cookie")
    assert any(line.startswith(f"{settings.access_cookie_name}=") and "Max-Age=0" in line for line in set_cookies)
    assert any(line.startswith(f"{settings.csrf_cookie_name}=") and "Max-Age=0" in line for line in set_cookies)
    assert _audit_events(security_harness) == [AuditEventType.MFA_PASSKEY_DELETED]
    _args, kwargs = security_harness.audit.calls[0]
    assert kwargs["metadata"] == {"passkey_uuid": EXISTING_PASSKEY.uuid}
    assert _job_payloads(security_harness)[0]["event"] == "mfa_changed"
    assert _job_payloads(security_harness)[0]["ctx"]["change_label"] == "Passkey removido"
    _assert_absent_from_side_effects(
        security_harness,
        LOGIN_SECRET,
        EXISTING_PASSKEY.credential_id,
        EXISTING_PASSKEY.public_key,
    )


def test_passkey_delete_rejects_the_last_factor_required_by_an_organization(
    security_harness: SecurityHarness,
) -> None:
    security_harness.mfa.totp = None

    response = security_harness.request(
        "DELETE",
        f"/api/v1/security/passkeys/{EXISTING_PASSKEY.uuid}",
    )

    _assert_problem(
        response,
        status=409,
        code="mfa_required_by_organization",
        detail="Você não pode remover o último fator de MFA exigido pela organização.",
    )
    assert security_harness.mfa.list_passkeys(USER.id) == [EXISTING_PASSKEY]
    assert security_harness.api_key.revoke_all_calls == []
    assert security_harness.audit.calls == []
    assert security_harness.job.calls == []


def test_passkey_delete_hides_another_users_credential_as_not_found(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request(
        "DELETE",
        f"/api/v1/security/passkeys/{OTHER_PASSKEY.uuid}",
    )

    _assert_problem(response, status=404, code="not_found", detail="Recurso não encontrado.")
    assert security_harness.mfa.delete_calls == [(OTHER_PASSKEY.uuid, USER.id)]
    assert OTHER_USER.email not in response.text
    assert security_harness.audit.calls == []
    assert security_harness.job.calls == []


def test_security_routes_reject_key_material_in_json_without_echoing_it(
    security_harness: SecurityHarness,
) -> None:
    response = security_harness.request(
        "POST",
        "/api/v1/security/pix",
        json={
            "pix_key": "person@example.com",
            "pix_merchant_name": "Person",
            "pix_merchant_city": "Recife",
            "api_key": INTEGRATION_SECRET,
        },
    )

    _assert_problem(
        response,
        status=400,
        code="malformed_credentials",
        detail="A chave deve ser enviada apenas por cookie ou cabeçalho Authorization Bearer.",
    )
    assert INTEGRATION_SECRET not in response.text
    assert security_harness.user.pix_calls == []


def test_security_openapi_exposes_post_only_totp_setup_and_strict_registration_models(
    security_harness: SecurityHarness,
) -> None:
    schema = security_harness.app.openapi()

    assert set(schema["paths"]["/api/v1/security/totp/setup"]) == {"post"}
    complete = schema["paths"]["/api/v1/security/passkeys/register/complete"]["post"]
    request_ref = complete["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert request_ref.endswith("/PasskeyRegistrationCompleteRequest")
    assert "422" in complete["responses"]

    complete_schema = schema["components"]["schemas"]["PasskeyRegistrationCompleteRequest"]
    credential_ref = complete_schema["properties"]["credential"]["$ref"]
    assert credential_ref.endswith("/WebAuthnRegistrationCredential")
    credential_schema = schema["components"]["schemas"]["WebAuthnRegistrationCredential"]
    assert credential_schema["additionalProperties"] is False
    assert credential_schema["properties"]["response"]["$ref"].endswith("/WebAuthnAuthenticatorAttestationResponse")

    begin = schema["paths"]["/api/v1/security/passkeys/register/begin"]["post"]
    begin_ref = begin["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    begin_schema = schema["components"]["schemas"][begin_ref.rsplit("/", 1)[-1]]
    assert begin_schema["properties"]["options"]["$ref"].endswith("/WebAuthnRegistrationOptions")
