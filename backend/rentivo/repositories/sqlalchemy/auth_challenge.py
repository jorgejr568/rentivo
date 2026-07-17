from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from ulid import ULID

from rentivo.models.auth_challenge import AuthChallenge
from rentivo.observability import suppress_tracing, traced
from rentivo.repositories.base import AuthChallengePersistenceError, AuthChallengeRepository


def _to_storage(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _as_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=UTC)


class SQLAlchemyAuthChallengeRepository(AuthChallengeRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def _rollback_safely(self) -> None:
        try:
            self.conn.rollback()
        except Exception:
            pass

    @staticmethod
    def _hydrate(row: RowMapping) -> AuthChallenge:
        return AuthChallenge(
            id=row["id"],
            uuid=row["uuid"],
            user_id=row["user_id"],
            phase=row["phase"],
            nonce_hash=row["nonce_hash"],
            allowed_methods=tuple(json.loads(row["allowed_methods"])),
            webauthn_challenge=row["webauthn_challenge"],
            failures=row["failures"],
            created_at=cast(datetime, _as_utc(row["created_at"])),
            expires_at=cast(datetime, _as_utc(row["expires_at"])),
            consumed_at=_as_utc(row["consumed_at"]),
        )

    @traced("auth_challenge_repo.create", record_exception_details=False)
    def create(self, challenge: AuthChallenge) -> AuthChallenge:
        challenge_uuid = challenge.uuid or str(ULID())
        persistence_error: AuthChallengePersistenceError | None = None
        try:
            with suppress_tracing():
                self.conn.execute(
                    text(
                        "INSERT INTO auth_challenges (uuid, user_id, phase, nonce_hash, allowed_methods, "
                        "webauthn_challenge, failures, expires_at, created_at, consumed_at) "
                        "VALUES (:uuid, :user_id, :phase, :nonce_hash, :allowed_methods, "
                        ":webauthn_challenge, :failures, :expires_at, :created_at, :consumed_at)"
                    ),
                    {
                        "uuid": challenge_uuid,
                        "user_id": challenge.user_id,
                        "phase": challenge.phase,
                        "nonce_hash": challenge.nonce_hash,
                        "allowed_methods": json.dumps(challenge.allowed_methods),
                        "webauthn_challenge": challenge.webauthn_challenge,
                        "failures": challenge.failures,
                        "expires_at": _to_storage(challenge.expires_at),
                        "created_at": _to_storage(challenge.created_at),
                        "consumed_at": _to_storage(challenge.consumed_at),
                    },
                )
            self.conn.commit()
        except SQLAlchemyError:
            self._rollback_safely()
            persistence_error = AuthChallengePersistenceError("Authentication challenge persistence failed")
        except BaseException:
            self.conn.rollback()
            raise
        if persistence_error is not None:
            raise persistence_error
        saved = self.get_by_uuid(challenge_uuid)
        if saved is None:
            raise AuthChallengePersistenceError("Authentication challenge persistence failed")
        return saved

    @traced("auth_challenge_repo.get_by_uuid", record_exception_details=False)
    def get_by_uuid(self, uuid: str) -> AuthChallenge | None:
        persistence_error: AuthChallengePersistenceError | None = None
        row = None
        try:
            row = (
                self.conn.execute(
                    text("SELECT * FROM auth_challenges WHERE uuid = :uuid"),
                    {"uuid": uuid},
                )
                .mappings()
                .one_or_none()
            )
        except SQLAlchemyError:
            self._rollback_safely()
            persistence_error = AuthChallengePersistenceError("Authentication challenge lookup failed")
        if persistence_error is not None:
            raise persistence_error
        return None if row is None else self._hydrate(row)

    @traced("auth_challenge_repo.increment_failures", record_exception_details=False)
    def increment_failures(self, uuid: str, phase: str, failed_at: datetime) -> bool:
        persistence_error: AuthChallengePersistenceError | None = None
        updated = False
        try:
            result = self.conn.execute(
                text(
                    "UPDATE auth_challenges SET failures = failures + 1 "
                    "WHERE uuid = :uuid AND phase = :phase AND consumed_at IS NULL "
                    "AND expires_at > :failed_at"
                ),
                {
                    "uuid": uuid,
                    "phase": phase,
                    "failed_at": _to_storage(failed_at),
                },
            )
            self.conn.commit()
            updated = result.rowcount > 0
        except SQLAlchemyError:
            self._rollback_safely()
            persistence_error = AuthChallengePersistenceError("Authentication challenge update failed")
        if persistence_error is not None:
            raise persistence_error
        return updated

    @traced("auth_challenge_repo.set_webauthn", record_exception_details=False)
    def set_webauthn_challenge(
        self,
        uuid: str,
        phase: str,
        webauthn_challenge: bytes,
        updated_at: datetime,
    ) -> bool:
        persistence_error: AuthChallengePersistenceError | None = None
        updated = False
        try:
            result = self.conn.execute(
                text(
                    "UPDATE auth_challenges SET webauthn_challenge = :webauthn_challenge "
                    "WHERE uuid = :uuid AND phase = :phase AND consumed_at IS NULL "
                    "AND expires_at > :updated_at"
                ),
                {
                    "uuid": uuid,
                    "phase": phase,
                    "webauthn_challenge": webauthn_challenge,
                    "updated_at": _to_storage(updated_at),
                },
            )
            self.conn.commit()
            updated = result.rowcount > 0
        except SQLAlchemyError:
            self._rollback_safely()
            persistence_error = AuthChallengePersistenceError("Authentication challenge update failed")
        if persistence_error is not None:
            raise persistence_error
        return updated

    @traced("auth_challenge_repo.consume", record_exception_details=False)
    def consume(self, uuid: str, phase: str, consumed_at: datetime) -> bool:
        persistence_error: AuthChallengePersistenceError | None = None
        consumed = False
        try:
            result = self.conn.execute(
                text(
                    "UPDATE auth_challenges SET consumed_at = :consumed_at "
                    "WHERE uuid = :uuid AND phase = :phase AND consumed_at IS NULL "
                    "AND expires_at > :consumed_at"
                ),
                {
                    "uuid": uuid,
                    "phase": phase,
                    "consumed_at": _to_storage(consumed_at),
                },
            )
            self.conn.commit()
            consumed = result.rowcount > 0
        except SQLAlchemyError:
            self._rollback_safely()
            persistence_error = AuthChallengePersistenceError("Authentication challenge consumption failed")
        if persistence_error is not None:
            raise persistence_error
        return consumed
