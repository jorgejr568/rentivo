from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from unittest.mock import MagicMock

import pytest

from rentivo.models.api_key import APIKey, APIKeyGrant
from rentivo.services.api_key_service import APIKeyService

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
RANDOM_SECRET = "aBcD" + ("x" * 37) + "yZ"
FULL_SECRET = f"rntv-v1-{RANDOM_SECRET}"


class RecordingRepository:
    def __init__(self) -> None:
        self.saved: APIKey | None = None
        self.lookups: list[bytes] = []

    def create(
        self,
        api_key: APIKey,
        *,
        scopes: frozenset[str],
        grants: tuple[APIKeyGrant, ...],
    ) -> APIKey:
        self.saved = api_key.model_copy(update={"id": 1, "scopes": scopes, "grants": grants})
        return self.saved

    def get_by_secret_hash(self, secret_hash: bytes) -> APIKey | None:
        self.lookups.append(secret_hash)
        if self.saved is not None and self.saved.secret_hash == secret_hash:
            return self.saved
        return None

    def touch_last_used(self, api_key_id: int, used_at: datetime) -> bool:
        return True


@pytest.fixture()
def repository() -> RecordingRepository:
    return RecordingRepository()


@pytest.fixture()
def service(repository: RecordingRepository) -> APIKeyService:
    return APIKeyService(
        repository=repository,
        user_repository=MagicMock(),
        organization_repository=MagicMock(),
        now=lambda: NOW,
        token_factory=lambda byte_count: RANDOM_SECRET,
        deployed_scopes=frozenset({"profile:read"}),
    )


def test_credential_uses_versioned_url_safe_format_and_32_random_bytes(
    repository: RecordingRepository,
) -> None:
    requested_bytes: list[int] = []

    def token_factory(byte_count: int) -> str:
        requested_bytes.append(byte_count)
        return RANDOM_SECRET

    service = APIKeyService(
        repository=repository,
        user_repository=MagicMock(),
        organization_repository=MagicMock(),
        now=lambda: NOW,
        token_factory=token_factory,
        deployed_scopes=frozenset({"profile:read"}),
    )

    issued = service.issue_login(user_id=7, name="Web login")

    assert issued.secret == FULL_SECRET
    assert requested_bytes == [32]
    assert len(issued.secret.removeprefix("rntv-v1-")) == 43


def test_invalid_token_factory_output_is_rejected(repository: RecordingRepository) -> None:
    service = APIKeyService(
        repository=repository,
        user_repository=MagicMock(),
        organization_repository=MagicMock(),
        now=lambda: NOW,
        token_factory=lambda byte_count: "not-url-safe!",
        deployed_scopes=frozenset({"profile:read"}),
    )

    with pytest.raises(RuntimeError, match="invalid credential"):
        service.issue_login(user_id=7, name="Web login")


def test_complete_credential_is_hashed_and_only_random_component_hints_are_saved(
    service: APIKeyService,
    repository: RecordingRepository,
) -> None:
    issued = service.issue_login(user_id=7, name="Web login")

    assert repository.saved is not None
    assert repository.saved.secret_hash == sha256(FULL_SECRET.encode()).digest()
    assert issued.key.key_start == "aBcD"
    assert issued.key.key_end == "yZ"
    assert "rntv" not in issued.key.key_start


def test_secret_is_disclosed_only_on_issue_result_and_never_serialized(
    service: APIKeyService,
    repository: RecordingRepository,
) -> None:
    issued = service.issue_login(user_id=7, name="Web login")

    assert repository.saved is not None
    assert not hasattr(repository.saved, "secret")
    assert "secret" not in repository.saved.model_dump()
    assert "secret_hash" not in repository.saved.model_dump()
    assert issued.secret == FULL_SECRET


@pytest.mark.parametrize(
    "credential",
    [
        "",
        RANDOM_SECRET,
        f"rntv-v2-{RANDOM_SECRET}",
        "rntv-v1-too-short",
        f"rntv-v1-{'x' * 42}",
        f"rntv-v1-{'x' * 44}",
        f"rntv-v1-{'x' * 42}!",
        f"rntv-v1-{'x' * 42} ",
        f" rntv-v1-{'x' * 43}",
    ],
)
def test_malformed_or_unsupported_credentials_are_rejected_before_lookup(
    service: APIKeyService,
    repository: RecordingRepository,
    credential: str,
) -> None:
    assert service.authenticate(credential) is None
    assert repository.lookups == []


def test_well_formed_credential_is_hashed_before_repository_lookup(
    service: APIKeyService,
    repository: RecordingRepository,
) -> None:
    assert service.authenticate(FULL_SECRET) is None

    assert repository.lookups == [sha256(FULL_SECRET.encode()).digest()]


def test_raw_secret_and_digest_are_absent_from_logs(
    service: APIKeyService,
    repository: RecordingRepository,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("DEBUG"):
        issued = service.issue_integration(
            user_id=7,
            name="Accounting export",
            scopes={"profile:read"},
            grants=[APIKeyGrant(resource_type="user", resource_id=7)],
            expires_at=NOW + timedelta(days=90),
        )
        assert service.authenticate(issued.secret) is not None

    assert repository.saved is not None
    assert issued.secret not in caplog.text
    assert repository.saved.secret_hash.hex() not in caplog.text
