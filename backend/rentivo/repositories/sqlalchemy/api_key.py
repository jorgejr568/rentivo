from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.models.api_key import APIKey, APIKeyGrant
from rentivo.observability import traced
from rentivo.repositories.base import APIKeyRepository


def _to_storage(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _as_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=UTC)


class SQLAlchemyAPIKeyRepository(APIKeyRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def _hydrate(self, row: RowMapping) -> APIKey:
        scopes = self.conn.execute(
            text("SELECT scope FROM api_key_scopes WHERE api_key_id = :id ORDER BY scope"),
            {"id": row["id"]},
        ).scalars()
        grant_rows = (
            self.conn.execute(
                text(
                    "SELECT resource_type, resource_id FROM api_key_resource_grants "
                    "WHERE api_key_id = :id ORDER BY resource_type, resource_id"
                ),
                {"id": row["id"]},
            )
            .mappings()
            .all()
        )
        return APIKey(
            id=row["id"],
            uuid=row["uuid"],
            user_id=row["user_id"],
            name=row["name"],
            secret_hash=row["secret_hash"],
            key_start=row["key_start"],
            key_end=row["key_end"],
            is_login_token=bool(row["is_login_token"]),
            scopes=frozenset(scopes),
            grants=tuple(APIKeyGrant(**grant_row) for grant_row in grant_rows),
            expires_at=cast(datetime, _as_utc(row["expires_at"])),
            last_used_at=_as_utc(row["last_used_at"]),
            created_at=_as_utc(row["created_at"]),
            revoked_at=_as_utc(row["revoked_at"]),
        )

    def _insert_children(
        self,
        api_key_id: int,
        scopes: frozenset[str],
        grants: tuple[APIKeyGrant, ...],
    ) -> None:
        for scope in sorted(scopes):
            self.conn.execute(
                text("INSERT INTO api_key_scopes (api_key_id, scope) VALUES (:api_key_id, :scope)"),
                {"api_key_id": api_key_id, "scope": scope},
            )
        for grant in grants:
            self.conn.execute(
                text(
                    "INSERT INTO api_key_resource_grants (api_key_id, resource_type, resource_id) "
                    "VALUES (:api_key_id, :resource_type, :resource_id)"
                ),
                {
                    "api_key_id": api_key_id,
                    "resource_type": grant.resource_type,
                    "resource_id": grant.resource_id,
                },
            )

    @traced("api_key_repo.create")
    def create(
        self,
        api_key: APIKey,
        *,
        scopes: frozenset[str],
        grants: tuple[APIKeyGrant, ...],
    ) -> APIKey:
        key_uuid = api_key.uuid or str(ULID())
        created_at = api_key.created_at or datetime.now(UTC)
        try:
            result = self.conn.execute(
                text(
                    "INSERT INTO api_keys (uuid, user_id, name, secret_hash, key_start, key_end, "
                    "is_login_token, expires_at, last_used_at, created_at, revoked_at) "
                    "VALUES (:uuid, :user_id, :name, :secret_hash, :key_start, :key_end, "
                    ":is_login_token, :expires_at, :last_used_at, :created_at, :revoked_at)"
                ),
                {
                    "uuid": key_uuid,
                    "user_id": api_key.user_id,
                    "name": api_key.name,
                    "secret_hash": api_key.secret_hash,
                    "key_start": api_key.key_start,
                    "key_end": api_key.key_end,
                    "is_login_token": api_key.is_login_token,
                    "expires_at": _to_storage(api_key.expires_at),
                    "last_used_at": _to_storage(api_key.last_used_at),
                    "created_at": _to_storage(created_at),
                    "revoked_at": _to_storage(api_key.revoked_at),
                },
            )
            self._insert_children(cast(int, result.lastrowid), scopes, grants)
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise
        return cast(APIKey, self.get_by_secret_hash(api_key.secret_hash))

    @traced("api_key_repo.get_by_secret_hash")
    def get_by_secret_hash(self, secret_hash: bytes) -> APIKey | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM api_keys WHERE secret_hash = :secret_hash"),
                {"secret_hash": secret_hash},
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else self._hydrate(row)

    @traced("api_key_repo.get_integration_by_uuid")
    def get_integration_by_uuid(self, user_id: int, uuid: str) -> APIKey | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM api_keys WHERE user_id = :user_id AND uuid = :uuid AND is_login_token = 0"),
                {"user_id": user_id, "uuid": uuid},
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else self._hydrate(row)

    @traced("api_key_repo.list_integrations")
    def list_integrations(self, user_id: int) -> list[APIKey]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT * FROM api_keys WHERE user_id = :user_id AND is_login_token = 0 "
                    "ORDER BY created_at DESC, id DESC"
                ),
                {"user_id": user_id},
            )
            .mappings()
            .all()
        )
        return [self._hydrate(row) for row in rows]

    @traced("api_key_repo.update_integration")
    def update_integration(
        self,
        api_key: APIKey,
        *,
        scopes: frozenset[str],
        grants: tuple[APIKeyGrant, ...],
    ) -> APIKey | None:
        try:
            api_key_id = self.conn.execute(
                text("SELECT id FROM api_keys WHERE uuid = :uuid AND user_id = :user_id AND is_login_token = 0"),
                {"uuid": api_key.uuid, "user_id": api_key.user_id},
            ).scalar_one_or_none()
            if api_key_id is None:
                self.conn.rollback()
                return None
            self.conn.execute(
                text("UPDATE api_keys SET name = :name WHERE id = :id"),
                {"name": api_key.name, "id": api_key_id},
            )
            self.conn.execute(text("DELETE FROM api_key_scopes WHERE api_key_id = :id"), {"id": api_key_id})
            self.conn.execute(
                text("DELETE FROM api_key_resource_grants WHERE api_key_id = :id"),
                {"id": api_key_id},
            )
            self._insert_children(api_key_id, scopes, grants)
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise
        return self.get_integration_by_uuid(api_key.user_id, api_key.uuid)

    @traced("api_key_repo.delete_login_token")
    def delete_login_token(self, api_key_id: int) -> bool:
        result = self.conn.execute(
            text("DELETE FROM api_keys WHERE id = :id AND is_login_token = 1"),
            {"id": api_key_id},
        )
        self.conn.commit()
        return result.rowcount > 0

    @traced("api_key_repo.revoke_integration")
    def revoke_integration(self, user_id: int, uuid: str, revoked_at: datetime) -> bool:
        result = self.conn.execute(
            text(
                "UPDATE api_keys SET revoked_at = COALESCE(revoked_at, :revoked_at) "
                "WHERE user_id = :user_id AND uuid = :uuid AND is_login_token = 0"
            ),
            {"user_id": user_id, "uuid": uuid, "revoked_at": _to_storage(revoked_at)},
        )
        self.conn.commit()
        return result.rowcount > 0

    @traced("api_key_repo.revoke_all_login_tokens")
    def revoke_all_login_tokens(self, user_id: int) -> int:
        result = self.conn.execute(
            text("DELETE FROM api_keys WHERE user_id = :user_id AND is_login_token = 1"),
            {"user_id": user_id},
        )
        self.conn.commit()
        return result.rowcount

    @traced("api_key_repo.delete_expired_login_tokens")
    def delete_expired_login_tokens(self, cutoff: datetime) -> int:
        result = self.conn.execute(
            text("DELETE FROM api_keys WHERE is_login_token = 1 AND expires_at <= :cutoff"),
            {"cutoff": _to_storage(cutoff)},
        )
        self.conn.commit()
        return result.rowcount

    @traced("api_key_repo.touch_last_used")
    def touch_last_used(self, api_key_id: int, used_at: datetime) -> bool:
        result = self.conn.execute(
            text("UPDATE api_keys SET last_used_at = :used_at WHERE id = :id"),
            {"used_at": _to_storage(used_at), "id": api_key_id},
        )
        self.conn.commit()
        return result.rowcount > 0
