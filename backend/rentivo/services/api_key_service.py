from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import compare_digest
from typing import Literal, NamedTuple

from rentivo.constants.api_scopes import (
    ALL_FIRST_PARTY_SCOPES,
    DEPLOYED_API_SCOPES,
    deployed_integration_scopes,
)
from rentivo.models.api_key import APIKey, APIKeyGrant
from rentivo.observability import traced
from rentivo.repositories.base import APIKeyRepository, OrganizationRepository, UserRepository

_CREDENTIAL_PREFIX = "rntv-v1-"
_CREDENTIAL_PATTERN = re.compile(r"rntv-v1-[A-Za-z0-9_-]{43}\Z")
_LOGIN_TTL = timedelta(hours=24)
_INTEGRATION_DEFAULT_TTL = timedelta(days=90)
_INTEGRATION_MAX_TTL = timedelta(days=365)
_LAST_USED_INTERVAL = timedelta(minutes=5)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("API-key datetime requires a timezone offset")
    return value.astimezone(UTC)


class IssuedAPIKey(NamedTuple):
    key: APIKey
    secret: str


class APIKeyService:
    def __init__(
        self,
        *,
        repository: APIKeyRepository,
        user_repository: UserRepository,
        organization_repository: OrganizationRepository,
        now: Callable[[], datetime] = _utcnow,
        token_factory: Callable[[int], str] = secrets.token_urlsafe,
        deployed_scopes: Iterable[str] = DEPLOYED_API_SCOPES,
    ) -> None:
        self.repository = repository
        self.user_repository = user_repository
        self.organization_repository = organization_repository
        self.now = now
        self.token_factory = token_factory
        self.integration_scopes = deployed_integration_scopes(deployed_scopes)

    @staticmethod
    def _digest(secret: str) -> bytes:
        return sha256(secret.encode()).digest()

    def _new_secret(self) -> tuple[str, str]:
        random_secret = self.token_factory(32)
        secret = f"{_CREDENTIAL_PREFIX}{random_secret}"
        if _CREDENTIAL_PATTERN.fullmatch(secret) is None:
            raise RuntimeError("API-key token factory returned an invalid credential")
        return secret, random_secret

    def _issue(
        self,
        *,
        user_id: int,
        name: str,
        is_login_token: bool,
        scopes: frozenset[str],
        grants: tuple[APIKeyGrant, ...],
        expires_at: datetime,
    ) -> IssuedAPIKey:
        secret, random_secret = self._new_secret()
        key = APIKey(
            user_id=user_id,
            name=name,
            secret_hash=self._digest(secret),
            key_start=random_secret[:4],
            key_end=random_secret[-2:],
            is_login_token=is_login_token,
            expires_at=expires_at,
            created_at=self.now(),
        )
        saved = self.repository.create(key, scopes=scopes, grants=grants)
        return IssuedAPIKey(key=saved, secret=secret)

    @staticmethod
    def _name(value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("API-key name is required")
        return name

    def _integration_metadata(
        self,
        *,
        user_id: int,
        name: str,
        scopes: Iterable[str],
        grants: Iterable[APIKeyGrant],
    ) -> tuple[str, frozenset[str], tuple[APIKeyGrant, ...]]:
        normalized_name = self._name(name)
        normalized_scopes = frozenset(str(scope) for scope in scopes)
        if not normalized_scopes or not normalized_scopes.issubset(self.integration_scopes):
            raise ValueError("API-key scopes must be deployed and integration-safe")

        normalized_grants = tuple(grants)
        if not normalized_grants or len(set(normalized_grants)) != len(normalized_grants):
            raise ValueError("API key must have distinct workspace grants")
        for grant in normalized_grants:
            if grant.resource_type == "user":
                if grant.resource_id != user_id:
                    raise ValueError("Personal workspace grant must belong to the key owner")
                continue
            if not self._has_live_organization_membership(grant.resource_id, user_id):
                raise ValueError("Organization workspace grant requires current membership")
        return normalized_name, normalized_scopes, normalized_grants

    def _has_live_organization_membership(self, organization_id: int, user_id: int) -> bool:
        return (
            self.organization_repository.get_by_id(organization_id) is not None
            and self.organization_repository.get_member(organization_id, user_id) is not None
        )

    @traced("api_key.issue_login", record_exception_details=False)
    def issue_login(self, *, user_id: int, name: str) -> IssuedAPIKey:
        now = _as_aware_utc(self.now())
        return self._issue(
            user_id=user_id,
            name=self._name(name),
            is_login_token=True,
            scopes=ALL_FIRST_PARTY_SCOPES,
            grants=(),
            expires_at=now + _LOGIN_TTL,
        )

    @traced("api_key.issue_integration", record_exception_details=False)
    def issue_integration(
        self,
        *,
        user_id: int,
        name: str,
        scopes: Iterable[str],
        grants: Iterable[APIKeyGrant],
        expires_at: datetime | None = None,
    ) -> IssuedAPIKey:
        _, normalized_name, normalized_scopes, normalized_grants, expiration = self._integration_configuration(
            user_id=user_id,
            name=name,
            scopes=scopes,
            grants=grants,
            expires_at=expires_at,
        )
        return self._issue(
            user_id=user_id,
            name=normalized_name,
            is_login_token=False,
            scopes=normalized_scopes,
            grants=normalized_grants,
            expires_at=expiration,
        )

    def validate_integration(
        self,
        *,
        user_id: int,
        name: str,
        scopes: Iterable[str],
        grants: Iterable[APIKeyGrant],
        expires_at: datetime | None = None,
    ) -> None:
        """Validate a prospective key without persisting it or reserving quota."""
        self._integration_configuration(
            user_id=user_id,
            name=name,
            scopes=scopes,
            grants=grants,
            expires_at=expires_at,
        )

    def _integration_configuration(
        self,
        *,
        user_id: int,
        name: str,
        scopes: Iterable[str],
        grants: Iterable[APIKeyGrant],
        expires_at: datetime | None,
    ) -> tuple[datetime, str, frozenset[str], tuple[APIKeyGrant, ...], datetime]:
        now = _as_aware_utc(self.now())
        normalized_name, normalized_scopes, normalized_grants = self._integration_metadata(
            user_id=user_id,
            name=name,
            scopes=scopes,
            grants=grants,
        )
        expiration = _as_aware_utc(expires_at) if expires_at is not None else now + _INTEGRATION_DEFAULT_TTL
        if expiration <= now or expiration > now + _INTEGRATION_MAX_TTL:
            raise ValueError("API-key expiration must be within one year")
        return now, normalized_name, normalized_scopes, normalized_grants, expiration

    @traced("api_key.authenticate", record_exception_details=False)
    def authenticate(self, secret: str) -> APIKey | None:
        if not isinstance(secret, str) or _CREDENTIAL_PATTERN.fullmatch(secret) is None:
            return None
        digest = self._digest(secret)
        key = self.repository.get_by_secret_hash(digest)
        now = _as_aware_utc(self.now())
        if key is None or not compare_digest(key.secret_hash, digest):
            return None
        if key.revoked_at is not None or _as_aware_utc(key.expires_at) <= now:
            return None
        if key.id is not None and (key.last_used_at is None or key.last_used_at <= now - _LAST_USED_INTERVAL):
            if self.repository.touch_last_used(key.id, now, now - _LAST_USED_INTERVAL):
                key = key.model_copy(update={"last_used_at": now})
        return key

    def can_access_resource(
        self,
        key: APIKey,
        resource_type: Literal["user", "organization"],
        resource_id: int,
    ) -> bool:
        if resource_type == "user":
            if resource_id != key.user_id:
                return False
            return key.is_login_token or APIKeyGrant(resource_type="user", resource_id=resource_id) in key.grants
        if resource_type != "organization":
            return False
        if (
            not key.is_login_token
            and APIKeyGrant(resource_type="organization", resource_id=resource_id) not in key.grants
        ):
            return False
        return self._has_live_organization_membership(resource_id, key.user_id)

    def update_integration(
        self,
        *,
        user_id: int,
        uuid: str,
        name: str,
        scopes: Iterable[str],
        grants: Iterable[APIKeyGrant],
    ) -> APIKey | None:
        existing = self.repository.get_integration_by_uuid(user_id, uuid)
        if existing is None or existing.revoked_at is not None:
            return None
        normalized_name, normalized_scopes, normalized_grants = self._integration_metadata(
            user_id=user_id,
            name=name,
            scopes=scopes,
            grants=grants,
        )
        return self.repository.update_integration(
            existing.model_copy(update={"name": normalized_name}),
            scopes=normalized_scopes,
            grants=normalized_grants,
        )

    def list_integrations(self, user_id: int) -> list[APIKey]:
        return self.repository.list_integrations(user_id)

    def get_integration(self, user_id: int, uuid: str) -> APIKey | None:
        return self.repository.get_integration_by_uuid(user_id, uuid)

    def logout(self, key: APIKey) -> bool:
        if not key.is_login_token or key.id is None:
            return False
        return self.repository.delete_login_token(key.id)

    def revoke_integration(self, user_id: int, uuid: str) -> bool:
        return self.repository.revoke_integration(user_id, uuid, self.now())

    def revoke_other_logins(self, user_id: int, current_key_uuid: str) -> int:
        return self.repository.revoke_other_login_tokens(user_id, current_key_uuid)

    def revoke_all_logins(self, user_id: int) -> int:
        return self.repository.revoke_all_login_tokens(user_id)

    def cleanup_expired_logins(self) -> int:
        return self.repository.delete_expired_login_tokens(self.now())
