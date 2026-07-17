from __future__ import annotations

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.encryption.base import EncryptionBackend
from rentivo.models.invite import Invite
from rentivo.observability import traced
from rentivo.repositories.base import InviteRepository
from rentivo.repositories.sqlalchemy._common import _now

# Shared SELECT that hydrates an invite with its organization + both user emails.
# Each caller appends its own WHERE/ORDER clause.
_INVITE_SELECT = (
    "SELECT i.*, o.name AS org_name, o.enforce_mfa, "
    "u1.email AS invited_email, u2.email AS invited_by_email "
    "FROM invites i "
    "JOIN organizations o ON i.organization_id = o.id "
    "JOIN users u1 ON i.invited_user_id = u1.id "
    "JOIN users u2 ON i.invited_by_user_id = u2.id "
)


class SQLAlchemyInviteRepository(InviteRepository):
    def __init__(self, conn: Connection, encryption: EncryptionBackend) -> None:
        self.conn = conn
        self.encryption = encryption

    def _row_to_invite(self, row: RowMapping) -> Invite:
        return Invite(
            id=row["id"],
            uuid=row["uuid"],
            organization_id=row["organization_id"],
            organization_name=row.get("org_name", ""),
            invited_user_id=row["invited_user_id"],
            invited_email=self.encryption.decrypt(row.get("invited_email", "") or ""),
            invited_by_user_id=row["invited_by_user_id"],
            invited_by_email=self.encryption.decrypt(row.get("invited_by_email", "") or ""),
            role=row["role"],
            status=row["status"],
            enforce_mfa=bool(row.get("enforce_mfa", False)),
            created_at=row["created_at"],
            responded_at=row.get("responded_at"),
        )

    @traced("invite_repo.create")
    def create(self, invite: Invite) -> Invite:
        invite_uuid = str(ULID())
        now = _now()
        self.conn.execute(
            text(
                "INSERT INTO invites (uuid, organization_id, invited_user_id, "
                "invited_by_user_id, role, status, created_at) "
                "VALUES (:uuid, :org_id, :invited_user_id, :invited_by_user_id, "
                ":role, :status, :created_at)"
            ),
            {
                "uuid": invite_uuid,
                "org_id": invite.organization_id,
                "invited_user_id": invite.invited_user_id,
                "invited_by_user_id": invite.invited_by_user_id,
                "role": invite.role,
                "status": invite.status,
                "created_at": now,
            },
        )
        self.conn.commit()
        created = self.get_by_uuid(invite_uuid)
        if created is None:
            raise RuntimeError("Failed to retrieve invite after create")
        return created

    @traced("invite_repo.get_by_uuid")
    def get_by_uuid(self, uuid: str) -> Invite | None:
        row = (
            self.conn.execute(
                text(_INVITE_SELECT + "WHERE i.uuid = :uuid"),
                {"uuid": uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_invite(row)

    @traced("invite_repo.list_pending_for_user")
    def list_pending_for_user(self, user_id: int) -> list[Invite]:
        rows = (
            self.conn.execute(
                text(
                    _INVITE_SELECT
                    + "WHERE i.invited_user_id = :uid AND i.status = 'pending' ORDER BY i.created_at DESC"
                ),
                {"uid": user_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_invite(row) for row in rows]

    @traced("invite_repo.list_by_organization")
    def list_by_organization(self, org_id: int) -> list[Invite]:
        rows = (
            self.conn.execute(
                text(_INVITE_SELECT + "WHERE i.organization_id = :org_id ORDER BY i.created_at DESC"),
                {"org_id": org_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_invite(row) for row in rows]

    @traced("invite_repo.update_status")
    def update_status(self, invite_id: int, status: str) -> None:
        self.conn.execute(
            text("UPDATE invites SET status = :status, responded_at = :responded_at WHERE id = :id"),
            {"status": status, "responded_at": _now(), "id": invite_id},
        )
        self.conn.commit()

    @traced("invite_repo.count_pending_for_user")
    def count_pending_for_user(self, user_id: int) -> int:
        result = (
            self.conn.execute(
                text("SELECT COUNT(*) AS cnt FROM invites WHERE invited_user_id = :uid AND status = 'pending'"),
                {"uid": user_id},
            )
            .mappings()
            .fetchone()
        )
        return result["cnt"] if result else 0

    @traced("invite_repo.has_pending_invite")
    def has_pending_invite(self, org_id: int, user_id: int) -> bool:
        result = (
            self.conn.execute(
                text(
                    "SELECT COUNT(*) AS cnt FROM invites "
                    "WHERE organization_id = :org_id AND invited_user_id = :uid "
                    "AND status = 'pending'"
                ),
                {"org_id": org_id, "uid": user_id},
            )
            .mappings()
            .fetchone()
        )
        return (result["cnt"] if result else 0) > 0
