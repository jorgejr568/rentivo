from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, call

import pytest

from rentivo.constants.api_scopes import ALL_FIRST_PARTY_SCOPES
from rentivo.models.api_key import APIKey
from rentivo.models.audit_log import AuditEventType
from rentivo.models.auth_challenge import AuthChallenge
from rentivo.models.user import User
from rentivo.services.api_key_service import IssuedAPIKey
from rentivo.services.audit_serializers import serialize_user
from rentivo.services.auth_challenge_service import IssuedAuthChallenge
from rentivo.services.login_service import LoginResult, LoginService

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
LOGIN_SECRET = "rntv-v1-aBcDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyZ"
CHALLENGE_NONCE = "challenge-nonce-that-must-stay-out-of-json"
CLIENT_IP = "203.0.113.42"
USER_AGENT = "Rentivo test browser/1.0"
BOOTSTRAP: dict[str, Any] = {
    "user": {"id": 7, "email": "user@example.com"},
    "capabilities": {"mfa_setup_required": False},
    "pending_invite_count": 0,
    "feature_flags": {},
    "analytics": {"gtm_container_id": "GTM-TEST"},
    "csrf_token": "csrf-token",
}


def _user() -> User:
    return User(id=7, email="user@example.com", password_hash="hash")


def _issued_key(user_id: int = 7) -> IssuedAPIKey:
    key = APIKey(
        id=11,
        uuid="01J2LOGINKEY00000000000000",
        user_id=user_id,
        name="Web login",
        secret_hash=b"digest",
        key_start="aBcD",
        key_end="yZ",
        is_login_token=True,
        scopes=ALL_FIRST_PARTY_SCOPES,
        expires_at=NOW + timedelta(days=1),
        created_at=NOW,
    )
    return IssuedAPIKey(key=key, secret=LOGIN_SECRET)


def _issued_challenge(methods: tuple[str, ...]) -> IssuedAuthChallenge:
    challenge = AuthChallenge(
        id=13,
        uuid="01J2LOGINCHALLENGE0000000",
        user_id=7,
        phase="login",
        nonce_hash=b"nonce-digest",
        allowed_methods=methods,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    return IssuedAuthChallenge(challenge=challenge, nonce=CHALLENGE_NONCE)


@pytest.fixture()
def dependencies() -> dict[str, MagicMock]:
    user_service = MagicMock()
    user_service.authenticate.return_value = _user()
    user_service.register_user.return_value = _user()

    api_key_service = MagicMock()
    api_key_service.issue_login.return_value = _issued_key()

    mfa_service = MagicMock()
    mfa_service.has_confirmed_totp.return_value = False
    mfa_service.list_passkeys.return_value = []
    mfa_service.user_requires_mfa_setup.return_value = False

    bootstrap_builder = MagicMock(return_value=BOOTSTRAP)
    return {
        "user_service": user_service,
        "api_key_service": api_key_service,
        "challenge_service": MagicMock(),
        "mfa_service": mfa_service,
        "audit_service": MagicMock(),
        "known_device_service": MagicMock(),
        "job_service": MagicMock(),
        "bootstrap_builder": bootstrap_builder,
    }


@pytest.fixture()
def service(dependencies: dict[str, MagicMock]) -> LoginService:
    return LoginService(
        user_service=dependencies["user_service"],
        api_key_service=dependencies["api_key_service"],
        challenge_service=dependencies["challenge_service"],
        mfa_service=dependencies["mfa_service"],
        audit_service=dependencies["audit_service"],
        known_device_service=dependencies["known_device_service"],
        job_service=dependencies["job_service"],
        bootstrap_builder=dependencies["bootstrap_builder"],
        public_app_url="https://rentivo.example",
    )


def _password_login(service: LoginService) -> LoginResult | None:
    return service.login_with_password(
        email="user@example.com",
        password="correct horse battery staple",
        client_ip=CLIENT_IP,
        user_agent=USER_AGENT,
    )


def test_password_login_without_mfa_issues_login_key_and_bootstrap(
    service: LoginService,
    dependencies: dict[str, MagicMock],
) -> None:
    result = _password_login(service)

    assert result is not None
    assert result.status == "authenticated"
    assert result.bootstrap == BOOTSTRAP
    assert result.challenge_id is None
    assert result.methods == ()
    assert result.access_credential == LOGIN_SECRET
    assert result.challenge_nonce is None
    assert result.user == _user()
    assert result.api_key == _issued_key().key
    dependencies["api_key_service"].issue_login.assert_called_once_with(user_id=7, name="Web login")
    dependencies["bootstrap_builder"].assert_called_once_with(
        user=_user(),
        api_key=_issued_key().key,
        mfa_setup_required=False,
    )


def test_authenticated_result_serialization_never_contains_login_secret(
    service: LoginService,
) -> None:
    result = _password_login(service)

    assert result is not None
    assert result.model_dump(mode="json") == {
        "status": "authenticated",
        "bootstrap": BOOTSTRAP,
        "challenge_id": None,
        "methods": [],
    }
    assert LOGIN_SECRET not in result.model_dump_json()
    assert LOGIN_SECRET not in repr(result)
    assert "access_credential" not in LoginResult.model_json_schema()["properties"]
    assert "challenge_nonce" not in LoginResult.model_json_schema()["properties"]


@pytest.mark.parametrize(
    ("has_totp", "passkey_count", "expected_methods"),
    [
        (True, 0, ("totp", "recovery")),
        (False, 1, ("passkey",)),
        (True, 2, ("totp", "recovery", "passkey")),
    ],
)
def test_password_login_with_mfa_issues_only_a_challenge_with_enrolled_methods(
    service: LoginService,
    dependencies: dict[str, MagicMock],
    has_totp: bool,
    passkey_count: int,
    expected_methods: tuple[str, ...],
) -> None:
    dependencies["mfa_service"].has_confirmed_totp.return_value = has_totp
    dependencies["mfa_service"].list_passkeys.return_value = [MagicMock() for _ in range(passkey_count)]
    dependencies["challenge_service"].issue.return_value = _issued_challenge(expected_methods)

    result = _password_login(service)

    assert result is not None
    assert result.status == "mfa_required"
    assert result.bootstrap is None
    assert result.challenge_id == "01J2LOGINCHALLENGE0000000"
    assert result.methods == expected_methods
    assert result.access_credential is None
    assert result.challenge_nonce == CHALLENGE_NONCE
    assert CHALLENGE_NONCE not in result.model_dump_json()
    dependencies["challenge_service"].issue.assert_called_once_with(
        user_id=7,
        phase="login",
        allowed_methods=expected_methods,
    )
    dependencies["api_key_service"].issue_login.assert_not_called()
    dependencies["bootstrap_builder"].assert_not_called()
    dependencies["known_device_service"].notify_if_new.assert_not_called()
    dependencies["mfa_service"].user_requires_mfa_setup.assert_not_called()


def test_org_mfa_setup_requirement_is_exposed_as_a_bootstrap_capability(
    service: LoginService,
    dependencies: dict[str, MagicMock],
) -> None:
    dependencies["mfa_service"].user_requires_mfa_setup.return_value = True
    bootstrap = {**BOOTSTRAP, "capabilities": {"mfa_setup_required": True}}
    dependencies["bootstrap_builder"].return_value = bootstrap

    result = _password_login(service)

    assert result is not None
    assert result.bootstrap == bootstrap
    dependencies["bootstrap_builder"].assert_called_once_with(
        user=_user(),
        api_key=_issued_key().key,
        mfa_setup_required=True,
    )


def test_successful_password_login_preserves_audit_device_and_analytics_semantics(
    service: LoginService,
    dependencies: dict[str, MagicMock],
) -> None:
    result = _password_login(service)

    assert result is not None
    actor, event_type = dependencies["audit_service"].safe_log_for.call_args.args
    assert (actor.user_id, actor.email, actor.source) == (7, "user@example.com", "web")
    assert (actor.api_key_uuid, actor.is_login_token) == ("01J2LOGINKEY00000000000000", True)
    assert event_type == AuditEventType.USER_LOGIN
    assert dependencies["audit_service"].safe_log_for.call_args.kwargs == {
        "entity_type": "user",
        "entity_id": 7,
        "new_state": {"user_id": 7, "email": "user@example.com"},
        "metadata": {"ip": CLIENT_IP},
    }
    dependencies["known_device_service"].notify_if_new.assert_called_once_with(
        user=_user(),
        user_agent=USER_AGENT,
        client_ip=CLIENT_IP,
        job_service=dependencies["job_service"],
    )
    assert result.analytics_event == {"event": "rentivo_login_success", "via": "password"}


def test_mfa_challenge_preserves_audit_semantics_without_complete_login_side_effects(
    service: LoginService,
    dependencies: dict[str, MagicMock],
) -> None:
    dependencies["mfa_service"].has_confirmed_totp.return_value = True
    dependencies["challenge_service"].issue.return_value = _issued_challenge(("totp", "recovery"))

    result = _password_login(service)

    assert result is not None
    actor, event_type = dependencies["audit_service"].safe_log_for.call_args.args
    assert (actor.user_id, actor.email, actor.source) == (7, "user@example.com", "web")
    assert (actor.api_key_uuid, actor.is_login_token) == (None, None)
    assert event_type == AuditEventType.MFA_CHALLENGE_ISSUED
    assert dependencies["audit_service"].safe_log_for.call_args.kwargs == {
        "entity_type": "user",
        "entity_id": 7,
        "metadata": {"ip": CLIENT_IP},
    }
    assert result.analytics_event is None
    dependencies["known_device_service"].notify_if_new.assert_not_called()


def test_signup_uses_the_same_authenticated_result_without_relabeling_signup_events(
    service: LoginService,
    dependencies: dict[str, MagicMock],
) -> None:
    result = service.signup(
        email="user@example.com",
        password="correct horse battery staple",
        client_ip=CLIENT_IP,
        user_agent=USER_AGENT,
    )

    assert result.status == "authenticated"
    assert result.bootstrap == BOOTSTRAP
    assert result.access_credential == LOGIN_SECRET
    dependencies["user_service"].register_user.assert_called_once_with(
        "user@example.com", "correct horse battery staple"
    )
    _, event_type = dependencies["audit_service"].safe_log_for.call_args.args
    assert event_type == AuditEventType.USER_SIGNUP
    assert dependencies["audit_service"].safe_log_for.call_args.kwargs["new_state"] == serialize_user(_user())
    assert result.analytics_event == {"event": "rentivo_signup_completed"}
    dependencies["job_service"].enqueue_for.assert_called_once()
    enqueue_actor, job_type, payload = dependencies["job_service"].enqueue_for.call_args.args
    assert (enqueue_actor.user_id, enqueue_actor.email, enqueue_actor.source) == (7, "user@example.com", "web")
    assert job_type == "email.send"
    assert payload == {
        "event": "welcome",
        "to_email": "user@example.com",
        "ctx": {
            "email": "user@example.com",
            "pix_setup_url": "https://rentivo.example/security/pix",
        },
    }
    dependencies["known_device_service"].notify_if_new.assert_not_called()


def test_complete_login_supports_post_mfa_callers_with_the_same_stable_payload(
    service: LoginService,
) -> None:
    result = service.complete_login(
        user=_user(),
        via="mfa",
        client_ip=CLIENT_IP,
        user_agent=USER_AGENT,
        audit_metadata={"mfa": True, "method": "totp"},
    )

    assert result.status == "authenticated"
    assert result.analytics_event == {"event": "rentivo_login_success", "via": "mfa"}


def test_login_alias_and_bootstrap_support_route_callers(
    service: LoginService,
    dependencies: dict[str, MagicMock],
) -> None:
    result = service.login(
        email="user@example.com",
        password="correct horse battery staple",
        client_ip=CLIENT_IP,
        user_agent=USER_AGENT,
    )
    principal = MagicMock(user=_user(), api_key=_issued_key().key)
    bootstrap = service.bootstrap(principal)

    assert result is not None
    assert result.status == "authenticated"
    assert bootstrap == BOOTSTRAP
    assert dependencies["bootstrap_builder"].call_args_list[-1].kwargs == {
        "user": _user(),
        "api_key": _issued_key().key,
        "mfa_setup_required": False,
    }


def test_invalid_credentials_are_indistinguishable_and_have_no_authenticated_side_effects(
    service: LoginService,
    dependencies: dict[str, MagicMock],
) -> None:
    dependencies["user_service"].authenticate.return_value = None

    results = [
        service.login_with_password(
            email="missing@example.com",
            password="wrong-one",
            client_ip=CLIENT_IP,
            user_agent=USER_AGENT,
        ),
        service.login_with_password(
            email="user@example.com",
            password="wrong-two",
            client_ip=CLIENT_IP,
            user_agent=USER_AGENT,
        ),
    ]

    assert results == [None, None]
    assert dependencies["user_service"].authenticate.call_args_list == [
        call("missing@example.com", "wrong-one"),
        call("user@example.com", "wrong-two"),
    ]
    dependencies["mfa_service"].has_confirmed_totp.assert_not_called()
    dependencies["challenge_service"].issue.assert_not_called()
    dependencies["api_key_service"].issue_login.assert_not_called()
    dependencies["bootstrap_builder"].assert_not_called()
    dependencies["audit_service"].safe_log_for.assert_not_called()
    dependencies["known_device_service"].notify_if_new.assert_not_called()


def test_login_side_effects_run_only_after_key_and_bootstrap_exist(
    service: LoginService,
    dependencies: dict[str, MagicMock],
) -> None:
    events: list[str] = []
    dependencies["api_key_service"].issue_login.side_effect = lambda **_: events.append("key") or _issued_key()
    dependencies["bootstrap_builder"].side_effect = lambda **_: events.append("bootstrap") or BOOTSTRAP
    dependencies["known_device_service"].notify_if_new.side_effect = lambda **_: events.append("known_device")
    dependencies["audit_service"].safe_log_for.side_effect = lambda *_args, **_kwargs: events.append("audit")

    result = _password_login(service)

    assert result is not None
    assert events == ["key", "bootstrap", "known_device", "audit"]


def test_key_issue_failure_does_not_report_or_run_post_login_side_effects(
    service: LoginService,
    dependencies: dict[str, MagicMock],
) -> None:
    dependencies["api_key_service"].issue_login.side_effect = RuntimeError("key persistence failed")

    with pytest.raises(RuntimeError, match="key persistence failed"):
        _password_login(service)

    dependencies["bootstrap_builder"].assert_not_called()
    dependencies["known_device_service"].notify_if_new.assert_not_called()
    dependencies["audit_service"].safe_log_for.assert_not_called()


@pytest.mark.parametrize("failure_point", ["bootstrap", "known_device"])
def test_failure_after_key_issue_deletes_the_undelivered_login_key(
    service: LoginService,
    dependencies: dict[str, MagicMock],
    failure_point: str,
) -> None:
    failure = RuntimeError(f"{failure_point} failed")
    if failure_point == "bootstrap":
        dependencies["bootstrap_builder"].side_effect = failure
    else:
        dependencies["known_device_service"].notify_if_new.side_effect = failure

    with pytest.raises(RuntimeError, match=f"{failure_point} failed"):
        _password_login(service)

    dependencies["api_key_service"].logout.assert_called_once_with(_issued_key().key)
    dependencies["audit_service"].safe_log_for.assert_not_called()


def test_challenge_issue_failure_never_audits_or_falls_through_to_key_issue(
    service: LoginService,
    dependencies: dict[str, MagicMock],
) -> None:
    dependencies["mfa_service"].has_confirmed_totp.return_value = True
    dependencies["challenge_service"].issue.side_effect = RuntimeError("challenge persistence failed")

    with pytest.raises(RuntimeError, match="challenge persistence failed"):
        _password_login(service)

    dependencies["audit_service"].safe_log_for.assert_not_called()
    dependencies["api_key_service"].issue_login.assert_not_called()
    dependencies["known_device_service"].notify_if_new.assert_not_called()


def test_signup_welcome_failure_does_not_fail_the_created_account(
    service: LoginService,
    dependencies: dict[str, MagicMock],
) -> None:
    dependencies["job_service"].enqueue_for.side_effect = RuntimeError("welcome failed")

    result = service.signup(
        email="user@example.com",
        password="correct horse battery staple",
        client_ip=CLIENT_IP,
        user_agent=USER_AGENT,
    )

    assert result.status == "authenticated"
    dependencies["api_key_service"].logout.assert_not_called()


def test_signup_failure_before_delivery_compensates_the_new_user(
    service: LoginService,
    dependencies: dict[str, MagicMock],
) -> None:
    dependencies["api_key_service"].issue_login.side_effect = RuntimeError("key failed")

    with pytest.raises(RuntimeError, match="key failed"):
        service.signup(
            email="user@example.com",
            password="correct horse battery staple",
            client_ip=CLIENT_IP,
            user_agent=USER_AGENT,
        )

    dependencies["user_service"].delete_new_user.assert_called_once_with(7)


def test_signup_compensation_failure_preserves_the_delivery_error(
    service: LoginService,
    dependencies: dict[str, MagicMock],
) -> None:
    dependencies["api_key_service"].issue_login.side_effect = RuntimeError("key failed")
    dependencies["user_service"].delete_new_user.side_effect = RuntimeError("delete failed")

    with pytest.raises(RuntimeError, match="key failed"):
        service.signup(
            email="user@example.com",
            password="correct horse battery staple",
            client_ip=CLIENT_IP,
            user_agent=USER_AGENT,
        )


def test_cleanup_failure_does_not_replace_original_post_issue_failure(
    service: LoginService,
    dependencies: dict[str, MagicMock],
) -> None:
    dependencies["bootstrap_builder"].side_effect = RuntimeError("bootstrap failed")
    dependencies["api_key_service"].logout.side_effect = RuntimeError("cleanup failed")

    with pytest.raises(RuntimeError, match="bootstrap failed"):
        _password_login(service)
