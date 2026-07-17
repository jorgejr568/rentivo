from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from rentivo.constants.api_scopes import ALL_FIRST_PARTY_SCOPES
from rentivo.models.api_key import APIKey, APIKeyGrant
from rentivo.models.organization import OrganizationMember
from rentivo.repositories.base import APIKeyRepository
from rentivo.services.api_key_service import APIKeyService, _utcnow

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
RANDOM_SECRET = "aBcD" + ("x" * 37) + "yZ"
DEPLOYED_SCOPES = frozenset({"profile:read", "organizations:read", "billings:read"})


class MutableClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


class TokenFactory:
    def __init__(self, value: str = RANDOM_SECRET) -> None:
        self.value = value
        self.requested_bytes: list[int] = []

    def __call__(self, byte_count: int) -> str:
        self.requested_bytes.append(byte_count)
        if len(self.requested_bytes) == 1:
            return self.value
        return "aBcD" + ("x" * 37) + f"{len(self.requested_bytes):02d}"


class FakeAPIKeyRepository(APIKeyRepository):
    def __init__(self) -> None:
        self.keys_by_hash: dict[bytes, APIKey] = {}
        self.next_id = 1
        self.secret_lookups: list[bytes] = []
        self.touch_calls: list[tuple[int, datetime]] = []
        self.deleted_login_ids: list[int] = []
        self.revoke_calls: list[tuple[int, str, datetime]] = []
        self.revoke_all_calls: list[int] = []
        self.cleanup_calls: list[datetime] = []

    def create(
        self,
        api_key: APIKey,
        *,
        scopes: frozenset[str],
        grants: tuple[APIKeyGrant, ...],
    ) -> APIKey:
        saved = api_key.model_copy(update={"id": self.next_id, "scopes": scopes, "grants": grants})
        self.next_id += 1
        self.keys_by_hash[saved.secret_hash] = saved
        return saved

    def get_by_secret_hash(self, secret_hash: bytes) -> APIKey | None:
        self.secret_lookups.append(secret_hash)
        return self.keys_by_hash.get(secret_hash)

    def get_integration_by_uuid(self, user_id: int, uuid: str) -> APIKey | None:
        return next(
            (
                key
                for key in self.keys_by_hash.values()
                if key.user_id == user_id and key.uuid == uuid and not key.is_login_token
            ),
            None,
        )

    def list_integrations(self, user_id: int) -> list[APIKey]:
        return [key for key in self.keys_by_hash.values() if key.user_id == user_id and not key.is_login_token]

    def update_integration(
        self,
        api_key: APIKey,
        *,
        scopes: frozenset[str],
        grants: tuple[APIKeyGrant, ...],
    ) -> APIKey | None:
        existing = self.get_integration_by_uuid(api_key.user_id, api_key.uuid)
        if existing is None:
            return None
        updated = existing.model_copy(update={"name": api_key.name, "scopes": scopes, "grants": grants})
        self.keys_by_hash[updated.secret_hash] = updated
        return updated

    def delete_login_token(self, api_key_id: int) -> bool:
        self.deleted_login_ids.append(api_key_id)
        match = next(
            (digest for digest, key in self.keys_by_hash.items() if key.id == api_key_id and key.is_login_token),
            None,
        )
        if match is None:
            return False
        del self.keys_by_hash[match]
        return True

    def revoke_integration(self, user_id: int, uuid: str, revoked_at: datetime) -> bool:
        self.revoke_calls.append((user_id, uuid, revoked_at))
        existing = self.get_integration_by_uuid(user_id, uuid)
        if existing is None:
            return False
        if existing.revoked_at is None:
            self.keys_by_hash[existing.secret_hash] = existing.model_copy(update={"revoked_at": revoked_at})
        return True

    def revoke_all_login_tokens(self, user_id: int) -> int:
        self.revoke_all_calls.append(user_id)
        matches = [digest for digest, key in self.keys_by_hash.items() if key.user_id == user_id and key.is_login_token]
        for digest in matches:
            del self.keys_by_hash[digest]
        return len(matches)

    def delete_expired_login_tokens(self, cutoff: datetime) -> int:
        self.cleanup_calls.append(cutoff)
        matches = [
            digest for digest, key in self.keys_by_hash.items() if key.is_login_token and key.expires_at <= cutoff
        ]
        for digest in matches:
            del self.keys_by_hash[digest]
        return len(matches)

    def touch_last_used(self, api_key_id: int, used_at: datetime) -> bool:
        self.touch_calls.append((api_key_id, used_at))
        for digest, key in self.keys_by_hash.items():
            if key.id == api_key_id:
                self.keys_by_hash[digest] = key.model_copy(update={"last_used_at": used_at})
                return True
        return False


@pytest.fixture()
def repository() -> FakeAPIKeyRepository:
    return FakeAPIKeyRepository()


@pytest.fixture()
def clock() -> MutableClock:
    return MutableClock()


@pytest.fixture()
def token_factory() -> TokenFactory:
    return TokenFactory()


@pytest.fixture()
def organization_repository() -> MagicMock:
    repository = MagicMock()
    repository.get_by_id.side_effect = lambda organization_id: (
        MagicMock(id=organization_id) if organization_id == 42 else None
    )
    repository.get_member.side_effect = lambda organization_id, user_id: (
        OrganizationMember(
            organization_id=organization_id,
            user_id=user_id,
            role="viewer",
        )
        if (organization_id, user_id) == (42, 7)
        else None
    )
    return repository


@pytest.fixture()
def service(
    repository: FakeAPIKeyRepository,
    clock: MutableClock,
    token_factory: TokenFactory,
    organization_repository: MagicMock,
) -> APIKeyService:
    return APIKeyService(
        repository=repository,
        user_repository=MagicMock(),
        organization_repository=organization_repository,
        now=clock,
        token_factory=token_factory,
        deployed_scopes=DEPLOYED_SCOPES,
    )


def _integration_args(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "user_id": 7,
        "name": "Accounting export",
        "scopes": {"profile:read"},
        "grants": [APIKeyGrant(resource_type="user", resource_id=7)],
        "expires_at": NOW + timedelta(days=90),
    }
    values.update(overrides)
    return values


def test_default_clock_is_utc_aware() -> None:
    assert _utcnow().tzinfo is UTC


def test_issue_login_has_fixed_24_hour_lifetime_and_every_scope(
    service: APIKeyService,
    repository: FakeAPIKeyRepository,
    token_factory: TokenFactory,
) -> None:
    issued = service.issue_login(user_id=7, name="Web login")

    assert issued.secret == f"rntv-v1-{RANDOM_SECRET}"
    assert issued.key.is_login_token is True
    assert issued.key.expires_at == NOW + timedelta(hours=24)
    assert issued.key.scopes == ALL_FIRST_PARTY_SCOPES
    assert issued.key.grants == ()
    assert token_factory.requested_bytes == [32]
    assert repository.get_by_secret_hash(issued.key.secret_hash) == issued.key


def test_login_activity_never_extends_absolute_expiration(
    service: APIKeyService,
    clock: MutableClock,
) -> None:
    issued = service.issue_login(user_id=7, name="Web login")
    original_expiry = issued.key.expires_at
    clock.advance(timedelta(hours=23, minutes=59))

    authenticated = service.authenticate(issued.secret)

    assert authenticated is not None
    assert authenticated.expires_at == original_expiry


def test_integration_defaults_to_90_days_when_expiration_is_omitted(
    service: APIKeyService,
) -> None:
    args = _integration_args()
    del args["expires_at"]

    issued = service.issue_integration(**args)

    assert issued.key.expires_at == NOW + timedelta(days=90)


@pytest.mark.parametrize("name", ["", "   ", "\n\t"])
def test_integration_requires_nonblank_name(service: APIKeyService, name: str) -> None:
    with pytest.raises(ValueError):
        service.issue_integration(**_integration_args(name=name))


@pytest.mark.parametrize(
    "scopes",
    [
        set(),
        {"security:manage"},
        {"account:write"},
        {"billings:write"},
        {"not-a-scope"},
    ],
)
def test_integration_rejects_empty_privileged_unknown_or_undeployed_scopes(
    service: APIKeyService, scopes: set[str]
) -> None:
    with pytest.raises(ValueError):
        service.issue_integration(**_integration_args(scopes=scopes))


def test_integration_accepts_only_deployed_integration_safe_scopes(
    service: APIKeyService,
) -> None:
    issued = service.issue_integration(**_integration_args(scopes={"profile:read", "organizations:read"}))

    assert issued.key.scopes == frozenset({"profile:read", "organizations:read"})


@pytest.mark.parametrize(
    "grants",
    [
        [],
        [APIKeyGrant(resource_type="user", resource_id=8)],
        [APIKeyGrant(resource_type="organization", resource_id=999)],
    ],
)
def test_integration_requires_an_owned_or_live_member_workspace(
    service: APIKeyService, grants: list[APIKeyGrant]
) -> None:
    with pytest.raises(ValueError):
        service.issue_integration(**_integration_args(grants=grants))


def test_integration_accepts_personal_and_current_organization_grants(
    service: APIKeyService,
) -> None:
    grants = [
        APIKeyGrant(resource_type="user", resource_id=7),
        APIKeyGrant(resource_type="organization", resource_id=42),
    ]

    issued = service.issue_integration(**_integration_args(grants=grants))

    assert issued.key.grants == tuple(grants)


def test_integration_rejects_membership_in_a_deleted_organization(
    service: APIKeyService,
    organization_repository: MagicMock,
) -> None:
    organization_repository.get_by_id.return_value = None
    organization_repository.get_by_id.side_effect = None

    with pytest.raises(ValueError):
        service.issue_integration(
            **_integration_args(grants=[APIKeyGrant(resource_type="organization", resource_id=42)])
        )


@pytest.mark.parametrize(
    "expires_at",
    [
        NOW - timedelta(microseconds=1),
        NOW,
        NOW + timedelta(days=365, microseconds=1),
    ],
)
def test_integration_expiration_must_be_future_and_at_most_one_year(
    service: APIKeyService, expires_at: datetime
) -> None:
    with pytest.raises(ValueError):
        service.issue_integration(**_integration_args(expires_at=expires_at))


def test_integration_accepts_expiration_at_exactly_one_year(
    service: APIKeyService,
) -> None:
    issued = service.issue_integration(**_integration_args(expires_at=NOW + timedelta(days=365)))

    assert issued.key.expires_at == NOW + timedelta(days=365)


def test_authenticate_rejects_expired_and_revoked_keys(
    service: APIKeyService,
    repository: FakeAPIKeyRepository,
    clock: MutableClock,
) -> None:
    expired = service.issue_login(user_id=7, name="Expired soon")
    clock.advance(timedelta(days=1))
    assert service.authenticate(expired.secret) is None

    clock.value = NOW
    revoked = service.issue_integration(**_integration_args())
    repository.revoke_integration(7, revoked.key.uuid, NOW)
    assert service.authenticate(revoked.secret) is None


def test_authenticate_touches_last_use_at_most_once_per_five_minutes(
    service: APIKeyService,
    repository: FakeAPIKeyRepository,
    clock: MutableClock,
) -> None:
    issued = service.issue_integration(**_integration_args())

    assert service.authenticate(issued.secret) is not None
    assert repository.touch_calls == [(issued.key.id, NOW)]

    clock.advance(timedelta(minutes=4, seconds=59))
    assert service.authenticate(issued.secret) is not None
    assert len(repository.touch_calls) == 1

    clock.advance(timedelta(seconds=1))
    assert service.authenticate(issued.secret) is not None
    assert repository.touch_calls[-1] == (issued.key.id, NOW + timedelta(minutes=5))


def test_login_key_access_uses_owner_and_live_membership(
    service: APIKeyService,
    organization_repository: MagicMock,
) -> None:
    key = service.issue_login(user_id=7, name="Web login").key

    assert service.can_access_resource(key, "user", 7) is True
    assert service.can_access_resource(key, "user", 8) is False
    assert service.can_access_resource(key, "organization", 42) is True

    organization_repository.get_member.return_value = None
    organization_repository.get_member.side_effect = None
    assert service.can_access_resource(key, "organization", 42) is False

    organization_repository.get_member.return_value = OrganizationMember(organization_id=42, user_id=7)
    organization_repository.get_by_id.return_value = None
    organization_repository.get_by_id.side_effect = None
    assert service.can_access_resource(key, "organization", 42) is False


def test_integration_access_requires_matching_grant_and_live_membership(
    service: APIKeyService,
    organization_repository: MagicMock,
) -> None:
    key = service.issue_integration(
        **_integration_args(
            grants=[
                APIKeyGrant(resource_type="user", resource_id=7),
                APIKeyGrant(resource_type="organization", resource_id=42),
            ]
        )
    ).key

    assert service.can_access_resource(key, "user", 7) is True
    assert service.can_access_resource(key, "user", 8) is False
    assert service.can_access_resource(key, "organization", 42) is True
    assert service.can_access_resource(key, "organization", 43) is False

    organization_repository.get_member.return_value = None
    organization_repository.get_member.side_effect = None
    assert service.can_access_resource(key, "organization", 42) is False


def test_resource_access_rejects_unknown_resource_type(service: APIKeyService) -> None:
    key = service.issue_login(user_id=7, name="Web login").key

    assert service.can_access_resource(key, "unknown", 7) is False  # type: ignore[arg-type]


def test_update_integration_changes_only_mutable_metadata(
    service: APIKeyService,
) -> None:
    issued = service.issue_integration(**_integration_args())
    updated = service.update_integration(
        user_id=7,
        uuid=issued.key.uuid,
        name="Read-only organization export",
        scopes={"organizations:read"},
        grants=[APIKeyGrant(resource_type="organization", resource_id=42)],
    )

    assert updated is not None
    assert updated.name == "Read-only organization export"
    assert updated.scopes == frozenset({"organizations:read"})
    assert updated.grants == (APIKeyGrant(resource_type="organization", resource_id=42),)
    assert updated.secret_hash == issued.key.secret_hash
    assert updated.expires_at == issued.key.expires_at


def test_update_integration_applies_creation_validation(
    service: APIKeyService,
) -> None:
    issued = service.issue_integration(**_integration_args())

    with pytest.raises(ValueError):
        service.update_integration(
            user_id=7,
            uuid=issued.key.uuid,
            name=" ",
            scopes={"security:manage"},
            grants=[APIKeyGrant(resource_type="organization", resource_id=999)],
        )


def test_update_integration_rejects_unknown_and_revoked_keys(
    service: APIKeyService,
    repository: FakeAPIKeyRepository,
) -> None:
    assert (
        service.update_integration(
            user_id=7,
            uuid="missing",
            name="Missing",
            scopes={"profile:read"},
            grants=[APIKeyGrant(resource_type="user", resource_id=7)],
        )
        is None
    )

    issued = service.issue_integration(**_integration_args())
    repository.revoke_integration(7, issued.key.uuid, NOW)
    assert (
        service.update_integration(
            user_id=7,
            uuid=issued.key.uuid,
            name="Revoked",
            scopes={"profile:read"},
            grants=[APIKeyGrant(resource_type="user", resource_id=7)],
        )
        is None
    )


def test_list_integrations_returns_only_owned_visible_keys(service: APIKeyService) -> None:
    service.issue_login(user_id=7, name="Browser")
    integration = service.issue_integration(**_integration_args())
    service.issue_integration(**_integration_args(user_id=8, grants=[APIKeyGrant(resource_type="user", resource_id=8)]))

    assert service.list_integrations(7) == [integration.key]


def test_logout_deletes_only_the_current_login_token(
    service: APIKeyService,
    repository: FakeAPIKeyRepository,
) -> None:
    first = service.issue_login(user_id=7, name="Browser one")
    second = service.issue_login(user_id=7, name="Browser two")
    integration = service.issue_integration(**_integration_args())

    assert service.logout(first.key) is True
    assert repository.deleted_login_ids == [first.key.id]
    assert service.authenticate(first.secret) is None
    assert service.authenticate(second.secret) is not None
    assert service.logout(integration.key) is False
    assert repository.deleted_login_ids == [first.key.id]


def test_integration_revocation_is_idempotent(
    service: APIKeyService,
) -> None:
    issued = service.issue_integration(**_integration_args())

    assert service.revoke_integration(7, issued.key.uuid) is True
    assert service.revoke_integration(7, issued.key.uuid) is True
    assert service.authenticate(issued.secret) is None


def test_revoking_an_unknown_integration_returns_false(service: APIKeyService) -> None:
    assert service.revoke_integration(7, "missing") is False


def test_revoke_all_logins_preserves_integration_keys(
    service: APIKeyService,
    repository: FakeAPIKeyRepository,
) -> None:
    first = service.issue_login(user_id=7, name="Browser one")
    second = service.issue_login(user_id=7, name="Browser two")
    other_user = service.issue_login(user_id=8, name="Other user")
    integration = service.issue_integration(**_integration_args())

    assert service.revoke_all_logins(7) == 2
    assert repository.revoke_all_calls == [7]
    assert service.authenticate(first.secret) is None
    assert service.authenticate(second.secret) is None
    assert service.authenticate(other_user.secret) is not None
    assert service.authenticate(integration.secret) is not None


def test_cleanup_removes_only_login_tokens_expired_at_the_cutoff(
    service: APIKeyService,
    repository: FakeAPIKeyRepository,
    clock: MutableClock,
) -> None:
    login = service.issue_login(user_id=7, name="Browser")
    integration = service.issue_integration(**_integration_args(expires_at=NOW + timedelta(hours=12)))
    clock.advance(timedelta(days=1))

    assert service.cleanup_expired_logins() == 1
    assert repository.cleanup_calls == [clock.value]
    assert service.authenticate(login.secret) is None
    assert repository.get_by_secret_hash(integration.key.secret_hash) is not None
