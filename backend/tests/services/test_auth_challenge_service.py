from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

import pytest

from rentivo.models.auth_challenge import AuthChallenge
from rentivo.repositories.base import AuthChallengeRepository
from rentivo.services import auth_challenge_service as service_module
from rentivo.services.auth_challenge_service import AuthChallengeService

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
NONCE = "aBcD" + ("x" * 37) + "yZ"
CHALLENGE_UUID = "01K0AUTHCHALLENGE000000000"


class MutableClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


class TokenFactory:
    def __init__(self, value: str = NONCE) -> None:
        self.value = value
        self.requested_bytes: list[int] = []

    def __call__(self, byte_count: int) -> str:
        self.requested_bytes.append(byte_count)
        return self.value


class FakeAuthChallengeRepository(AuthChallengeRepository):
    def __init__(self) -> None:
        self.challenges: dict[str, AuthChallenge] = {}
        self.created: list[AuthChallenge] = []
        self.consume_calls: list[tuple[str, str, datetime]] = []
        self.failure_calls: list[tuple[str, str, datetime]] = []
        self.webauthn_calls: list[tuple[str, str, bytes, datetime]] = []
        self.consume_result_override: bool | None = None

    def create(self, challenge: AuthChallenge) -> AuthChallenge:
        saved = challenge.model_copy(
            update={
                "id": len(self.challenges) + 1,
                "uuid": challenge.uuid or CHALLENGE_UUID,
            }
        )
        self.challenges[saved.uuid] = saved
        self.created.append(saved)
        return saved

    def get_by_uuid(self, uuid: str) -> AuthChallenge | None:
        return self.challenges.get(uuid)

    def increment_failures(
        self,
        uuid: str,
        phase: str,
        failed_at: datetime,
        *,
        failure_limit: int | None = None,
    ) -> bool:
        challenge = self.challenges.get(uuid)
        if (
            challenge is None
            or challenge.phase != phase
            or challenge.consumed_at is not None
            or challenge.expires_at <= failed_at
            or (failure_limit is not None and challenge.failures >= failure_limit)
        ):
            return False
        self.failure_calls.append((uuid, phase, failed_at))
        failures = challenge.failures + 1
        consumed_at = failed_at if failure_limit is not None and failures >= failure_limit else None
        self.challenges[uuid] = challenge.model_copy(update={"failures": failures, "consumed_at": consumed_at})
        return True

    def set_webauthn_challenge(
        self,
        uuid: str,
        phase: str,
        webauthn_challenge: bytes,
        updated_at: datetime,
    ) -> bool:
        self.webauthn_calls.append((uuid, phase, webauthn_challenge, updated_at))
        challenge = self.challenges.get(uuid)
        if (
            challenge is None
            or challenge.phase != phase
            or challenge.consumed_at is not None
            or challenge.expires_at <= updated_at
        ):
            return False
        self.challenges[uuid] = challenge.model_copy(update={"webauthn_challenge": webauthn_challenge})
        return True

    def consume(self, uuid: str, phase: str, consumed_at: datetime) -> bool:
        self.consume_calls.append((uuid, phase, consumed_at))
        if self.consume_result_override is not None:
            return self.consume_result_override
        challenge = self.challenges.get(uuid)
        if (
            challenge is None
            or challenge.phase != phase
            or challenge.consumed_at is not None
            or challenge.expires_at <= consumed_at
        ):
            return False
        self.challenges[uuid] = challenge.model_copy(update={"consumed_at": consumed_at})
        return True


@pytest.fixture()
def clock() -> MutableClock:
    return MutableClock()


@pytest.fixture()
def token_factory() -> TokenFactory:
    return TokenFactory()


@pytest.fixture()
def repository() -> FakeAuthChallengeRepository:
    return FakeAuthChallengeRepository()


@pytest.fixture()
def service(
    repository: FakeAuthChallengeRepository,
    clock: MutableClock,
    token_factory: TokenFactory,
) -> AuthChallengeService:
    return AuthChallengeService(repository=repository, now=clock, token_factory=token_factory)


def issue_mfa(service: AuthChallengeService, **overrides: Any):
    kwargs: dict[str, Any] = {
        "user_id": 7,
        "phase": "mfa",
        "allowed_methods": ("totp", "passkey"),
    }
    kwargs.update(overrides)
    return service.issue(**kwargs)


def test_default_clock_is_utc_aware() -> None:
    assert service_module._utcnow().tzinfo is UTC


def test_service_rejects_non_positive_ttl(repository: FakeAuthChallengeRepository) -> None:
    with pytest.raises(ValueError, match="TTL must be positive"):
        AuthChallengeService(repository=repository, ttl=timedelta(0))


def test_service_rejects_naive_clock(repository: FakeAuthChallengeRepository) -> None:
    service = AuthChallengeService(
        repository=repository,
        now=lambda: NOW.replace(tzinfo=None),
    )

    with pytest.raises(ValueError, match="timezone offset"):
        issue_mfa(service)


def test_issue_returns_raw_nonce_once_and_persists_only_its_sha256_digest(
    service: AuthChallengeService,
    repository: FakeAuthChallengeRepository,
    token_factory: TokenFactory,
) -> None:
    issued = issue_mfa(service)

    assert issued.nonce == NONCE
    assert issued.challenge == repository.created[0]
    assert issued.challenge.nonce_hash == sha256(NONCE.encode()).digest()
    assert NONCE not in repr(issued.challenge)
    assert "nonce_hash" not in issued.challenge.model_dump()
    assert token_factory.requested_bytes == [32]


def test_issue_sets_exact_five_minute_lifetime_and_preserves_allowed_methods(
    service: AuthChallengeService,
) -> None:
    issued = issue_mfa(service, allowed_methods=("passkey", "recovery"))

    assert issued.challenge.user_id == 7
    assert issued.challenge.phase == "mfa"
    assert issued.challenge.allowed_methods == ("passkey", "recovery")
    assert issued.challenge.created_at == NOW
    assert issued.challenge.expires_at == NOW + timedelta(minutes=5)
    assert issued.challenge.failures == 0
    assert issued.challenge.consumed_at is None


@pytest.mark.parametrize("webauthn_challenge", [None, b"server-side-webauthn-challenge"])
def test_issue_preserves_optional_webauthn_challenge_bytes(
    service: AuthChallengeService,
    webauthn_challenge: bytes | None,
) -> None:
    issued = issue_mfa(service, webauthn_challenge=webauthn_challenge)

    assert issued.challenge.webauthn_challenge == webauthn_challenge


def test_issue_supports_pre_user_oauth_state(service: AuthChallengeService) -> None:
    issued = service.issue(user_id=None, phase="oauth", allowed_methods=())

    assert issued.challenge.user_id is None
    assert issued.challenge.phase == "oauth"
    assert issued.challenge.allowed_methods == ()


def test_get_valid_rejects_exact_expiry_boundary(
    service: AuthChallengeService,
    clock: MutableClock,
) -> None:
    issued = issue_mfa(service)

    clock.advance(timedelta(minutes=5))
    assert (
        service.get_valid(
            issued.challenge.uuid,
            issued.nonce,
            expected_phase="mfa",
            expected_method="totp",
        )
        is None
    )


def test_get_valid_rejects_unknown_and_consumed_challenges(
    service: AuthChallengeService,
) -> None:
    issued = issue_mfa(service)
    consumed = issued.challenge.model_copy(update={"consumed_at": NOW})
    service.repository.challenges[issued.challenge.uuid] = consumed

    assert (
        service.get_valid(
            "01K0MISSINGCHALLENGE000000",
            issued.nonce,
            expected_phase="mfa",
            expected_method="totp",
        )
        is None
    )
    assert (
        service.get_valid(
            issued.challenge.uuid,
            issued.nonce,
            expected_phase="mfa",
            expected_method="totp",
        )
        is None
    )


@pytest.mark.parametrize(
    ("expected_phase", "expected_method"),
    [("oauth", None), ("mfa", "recovery")],
)
def test_get_valid_binds_expected_phase_and_method(
    service: AuthChallengeService,
    repository: FakeAuthChallengeRepository,
    expected_phase: str,
    expected_method: str | None,
) -> None:
    issued = issue_mfa(service, allowed_methods=("totp", "passkey"))

    assert (
        service.get_valid(
            issued.challenge.uuid,
            issued.nonce,
            expected_phase=expected_phase,
            expected_method=expected_method,
        )
        is None
    )
    assert repository.failure_calls == []


def test_wrong_nonce_uses_constant_time_comparison_and_counts_failure(
    service: AuthChallengeService,
    repository: FakeAuthChallengeRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = issue_mfa(service)
    calls: list[tuple[bytes, bytes]] = []

    def recording_compare_digest(left: bytes, right: bytes) -> bool:
        calls.append((left, right))
        return False

    monkeypatch.setattr(service_module, "compare_digest", recording_compare_digest)

    assert (
        service.get_valid(
            issued.challenge.uuid,
            "wrong-nonce",
            expected_phase="mfa",
            expected_method="totp",
        )
        is None
    )
    assert calls == [(issued.challenge.nonce_hash, sha256(b"wrong-nonce").digest())]
    assert repository.failure_calls == [(issued.challenge.uuid, "mfa", NOW)]
    assert repository.challenges[issued.challenge.uuid].failures == 1


def test_expired_or_consumed_challenge_does_not_count_nonce_failures(
    service: AuthChallengeService,
    repository: FakeAuthChallengeRepository,
    clock: MutableClock,
) -> None:
    expired = issue_mfa(service)
    clock.advance(timedelta(minutes=5, microseconds=1))
    assert (
        service.get_valid(
            expired.challenge.uuid,
            "wrong-nonce",
            expected_phase="mfa",
            expected_method="totp",
        )
        is None
    )

    clock.value = NOW
    consumed = issue_mfa(service)
    repository.challenges[consumed.challenge.uuid] = consumed.challenge.model_copy(update={"consumed_at": NOW})
    assert (
        service.get_valid(
            consumed.challenge.uuid,
            "wrong-nonce",
            expected_phase="mfa",
            expected_method="totp",
        )
        is None
    )
    assert repository.failure_calls == []


def test_challenge_is_single_use(
    service: AuthChallengeService,
    repository: FakeAuthChallengeRepository,
) -> None:
    issued = issue_mfa(service)

    first = service.consume(
        issued.challenge.uuid,
        issued.nonce,
        expected_phase="mfa",
        expected_method="totp",
    )
    second = service.consume(
        issued.challenge.uuid,
        issued.nonce,
        expected_phase="mfa",
        expected_method="totp",
    )

    assert first is not None
    assert first.user_id == 7
    assert second is None
    assert repository.consume_calls == [(issued.challenge.uuid, "mfa", NOW)]
    assert repository.challenges[issued.challenge.uuid].consumed_at == NOW


def test_consume_returns_none_when_atomic_repository_write_loses_race(
    service: AuthChallengeService,
    repository: FakeAuthChallengeRepository,
) -> None:
    issued = issue_mfa(service)
    repository.consume_result_override = False

    assert (
        service.consume(
            issued.challenge.uuid,
            issued.nonce,
            expected_phase="mfa",
            expected_method="totp",
        )
        is None
    )
    assert repository.consume_calls == [(issued.challenge.uuid, "mfa", NOW)]


def test_consume_wrong_nonce_counts_failure_without_attempting_consume(
    service: AuthChallengeService,
    repository: FakeAuthChallengeRepository,
) -> None:
    issued = issue_mfa(service)

    assert (
        service.consume(
            issued.challenge.uuid,
            "wrong-nonce",
            expected_phase="mfa",
            expected_method="totp",
        )
        is None
    )
    assert repository.failure_calls == [(issued.challenge.uuid, "mfa", NOW)]
    assert repository.consume_calls == []


def test_record_failure_exposes_invalid_mfa_attempt_through_service(
    service: AuthChallengeService,
    repository: FakeAuthChallengeRepository,
) -> None:
    issued = issue_mfa(service)

    assert (
        service.record_failure(
            issued.challenge.uuid,
            issued.nonce,
            expected_phase="mfa",
            expected_method="totp",
        )
        is True
    )
    assert repository.failure_calls == [(issued.challenge.uuid, "mfa", NOW)]
    assert repository.challenges[issued.challenge.uuid].failures == 1


def test_login_challenge_is_invalidated_after_five_persisted_failures(
    service: AuthChallengeService,
    repository: FakeAuthChallengeRepository,
) -> None:
    issued = issue_mfa(service, phase="login")

    for _attempt in range(5):
        assert (
            service.record_failure(
                issued.challenge.uuid,
                issued.nonce,
                expected_phase="login",
                expected_method="totp",
            )
            is True
        )

    persisted = repository.challenges[issued.challenge.uuid]
    assert persisted.failures == 5
    assert persisted.consumed_at == NOW
    assert (
        service.get_valid(
            issued.challenge.uuid,
            issued.nonce,
            expected_phase="login",
            expected_method="totp",
        )
        is None
    )
    assert (
        service.record_failure(
            issued.challenge.uuid,
            issued.nonce,
            expected_phase="login",
            expected_method="totp",
        )
        is False
    )


def test_record_failure_rejects_invalid_challenge(
    service: AuthChallengeService,
    repository: FakeAuthChallengeRepository,
) -> None:
    assert (
        service.record_failure(
            "01K0MISSINGCHALLENGE000000",
            NONCE,
            expected_phase="mfa",
            expected_method="totp",
        )
        is False
    )
    assert repository.failure_calls == []


def test_set_webauthn_challenge_is_nonce_phase_and_method_bound(
    service: AuthChallengeService,
    repository: FakeAuthChallengeRepository,
) -> None:
    issued = issue_mfa(service)

    updated = service.set_webauthn_challenge(
        issued.challenge.uuid,
        issued.nonce,
        expected_phase="mfa",
        webauthn_challenge=b"new-passkey-challenge",
    )

    assert updated is not None
    assert updated.webauthn_challenge == b"new-passkey-challenge"
    assert repository.webauthn_calls == [(issued.challenge.uuid, "mfa", b"new-passkey-challenge", NOW)]


def test_set_webauthn_challenge_rejects_challenge_without_passkey_method(
    service: AuthChallengeService,
    repository: FakeAuthChallengeRepository,
) -> None:
    issued = issue_mfa(service, allowed_methods=("totp",))

    assert (
        service.set_webauthn_challenge(
            issued.challenge.uuid,
            issued.nonce,
            expected_phase="mfa",
            webauthn_challenge=b"new-passkey-challenge",
        )
        is None
    )
    assert repository.webauthn_calls == []


def test_set_webauthn_challenge_returns_none_when_conditional_update_loses_race(
    service: AuthChallengeService,
    repository: FakeAuthChallengeRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = issue_mfa(service)
    monkeypatch.setattr(repository, "set_webauthn_challenge", lambda *args: False)

    assert (
        service.set_webauthn_challenge(
            issued.challenge.uuid,
            issued.nonce,
            expected_phase="mfa",
            webauthn_challenge=b"new-passkey-challenge",
        )
        is None
    )
