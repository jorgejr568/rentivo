from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from rentivo.models import APIKey, APIKeyGrant


def test_api_key_defaults_and_secret_hash_is_excluded_from_serialization() -> None:
    key = APIKey(
        user_id=7,
        name="Accounting export",
        secret_hash=b"x" * 32,
        key_start="aBcD",
        key_end="yZ",
        expires_at=datetime(2026, 10, 15, tzinfo=UTC),
    )

    assert key.id is None
    assert key.uuid == ""
    assert key.is_login_token is False
    assert key.scopes == frozenset()
    assert key.grants == ()
    assert key.last_used_at is None
    assert key.created_at is None
    assert key.revoked_at is None
    assert "secret_hash" not in key.model_dump()


def test_api_key_grant_is_frozen_and_restricts_resource_type() -> None:
    grant = APIKeyGrant(resource_type="organization", resource_id=42)

    with pytest.raises(ValidationError, match="frozen"):
        grant.resource_id = 43

    with pytest.raises(ValidationError):
        APIKeyGrant(resource_type="billing", resource_id=42)
