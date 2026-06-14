from __future__ import annotations

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.encryption.base import EncryptionBackend
from rentivo.models.organization import Organization, OrganizationMember
from rentivo.observability import traced
from rentivo.repositories.base import OrganizationRepository
from rentivo.repositories.sqlalchemy._common import _now


class SQLAlchemyOrganizationRepository(OrganizationRepository):
    def __init__(self, conn: Connection, encryption: EncryptionBackend) -> None:
        self.conn = conn
        self.encryption = encryption

    def _row_to_org(self, row: RowMapping) -> Organization:
        return Organization(
            id=row["id"],
            uuid=row["uuid"],
            name=row["name"],
            created_by=row["created_by"],
            enforce_mfa=bool(row.get("enforce_mfa", False)),
            pix_key=self.encryption.decrypt(row.get("pix_key", "") or ""),
            pix_merchant_name=self.encryption.decrypt(row.get("pix_merchant_name", "") or ""),
            pix_merchant_city=self.encryption.decrypt(row.get("pix_merchant_city", "") or ""),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row.get("deleted_at"),
        )

    @staticmethod
    def _row_to_member(row: RowMapping) -> OrganizationMember:
        return OrganizationMember(
            id=row["id"],
            organization_id=row["organization_id"],
            user_id=row["user_id"],
            role=row["role"],
            created_at=row["created_at"],
        )

    @traced("organization_repo.create")
    def create(self, org: Organization) -> Organization:
        org_uuid = str(ULID())
        now = _now()
        result = self.conn.execute(
            text(
                "INSERT INTO organizations (uuid, name, created_by, created_at, updated_at) "
                "VALUES (:uuid, :name, :created_by, :created_at, :updated_at)"
            ),
            {"uuid": org_uuid, "name": org.name, "created_by": org.created_by, "created_at": now, "updated_at": now},
        )
        org_id = result.lastrowid
        self.conn.commit()
        created = self.get_by_id(org_id)
        if created is None:
            raise RuntimeError(f"Failed to retrieve org after create (id={org_id})")
        return created

    @traced("organization_repo.get_by_id")
    def get_by_id(self, org_id: int) -> Organization | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM organizations WHERE id = :id AND deleted_at IS NULL"),
                {"id": org_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_org(row)

    @traced("organization_repo.get_by_uuid")
    def get_by_uuid(self, uuid: str) -> Organization | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM organizations WHERE uuid = :uuid AND deleted_at IS NULL"),
                {"uuid": uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_org(row)

    @traced("organization_repo.list_by_user")
    def list_by_user(self, user_id: int) -> list[Organization]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT o.* FROM organizations o "
                    "JOIN organization_members om ON o.id = om.organization_id "
                    "WHERE om.user_id = :uid AND o.deleted_at IS NULL "
                    "ORDER BY o.name"
                ),
                {"uid": user_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_org(row) for row in rows]

    @traced("organization_repo.update")
    def update(self, org: Organization) -> Organization:
        self.conn.execute(
            text(
                "UPDATE organizations SET name = :name, enforce_mfa = :enforce_mfa, "
                "pix_key = :pix_key, pix_merchant_name = :pix_merchant_name, "
                "pix_merchant_city = :pix_merchant_city, updated_at = :updated_at WHERE id = :id"
            ),
            {
                "name": org.name,
                "enforce_mfa": org.enforce_mfa,
                "pix_key": self.encryption.encrypt(org.pix_key),
                "pix_merchant_name": self.encryption.encrypt(org.pix_merchant_name),
                "pix_merchant_city": self.encryption.encrypt(org.pix_merchant_city),
                "updated_at": _now(),
                "id": org.id,
            },
        )
        self.conn.commit()
        if org.id is None:  # pragma: no cover
            raise ValueError("Cannot update org without an id")
        result = self.get_by_id(org.id)
        if result is None:
            raise RuntimeError(f"Failed to retrieve org after update (id={org.id})")
        return result

    @traced("organization_repo.delete")
    def delete(self, org_id: int) -> None:
        self.conn.execute(
            text("UPDATE organizations SET deleted_at = :deleted_at WHERE id = :id"),
            {"deleted_at": _now(), "id": org_id},
        )
        self.conn.commit()

    @traced("organization_repo.add_member")
    def add_member(self, org_id: int, user_id: int, role: str) -> OrganizationMember:
        now = _now()
        self.conn.execute(
            text(
                "INSERT INTO organization_members (organization_id, user_id, role, created_at) "
                "VALUES (:org_id, :user_id, :role, :created_at)"
            ),
            {"org_id": org_id, "user_id": user_id, "role": role, "created_at": now},
        )
        self.conn.commit()
        member = self.get_member(org_id, user_id)
        if member is None:
            raise RuntimeError("Failed to retrieve member after create")
        return member

    @traced("organization_repo.remove_member")
    def remove_member(self, org_id: int, user_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM organization_members WHERE organization_id = :org_id AND user_id = :user_id"),
            {"org_id": org_id, "user_id": user_id},
        )
        self.conn.commit()

    @traced("organization_repo.get_member")
    def get_member(self, org_id: int, user_id: int) -> OrganizationMember | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM organization_members WHERE organization_id = :org_id AND user_id = :user_id"),
                {"org_id": org_id, "user_id": user_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_member(row)

    @traced("organization_repo.list_members")
    def list_members(self, org_id: int) -> list[OrganizationMember]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT om.*, u.email FROM organization_members om "
                    "JOIN users u ON om.user_id = u.id "
                    "WHERE om.organization_id = :org_id ORDER BY om.created_at"
                ),
                {"org_id": org_id},
            )
            .mappings()
            .fetchall()
        )
        return [
            OrganizationMember(
                id=row["id"],
                organization_id=row["organization_id"],
                user_id=row["user_id"],
                email=self.encryption.decrypt(row.get("email", "") or ""),
                role=row["role"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    @traced("organization_repo.update_member_role")
    def update_member_role(self, org_id: int, user_id: int, role: str) -> None:
        self.conn.execute(
            text("UPDATE organization_members SET role = :role WHERE organization_id = :org_id AND user_id = :user_id"),
            {"role": role, "org_id": org_id, "user_id": user_id},
        )
        self.conn.commit()

    @traced("organization_repo.user_has_enforcing_org")
    def user_has_enforcing_org(self, user_id: int) -> bool:
        result = (
            self.conn.execute(
                text(
                    "SELECT COUNT(*) AS cnt FROM organizations o "
                    "JOIN organization_members om ON o.id = om.organization_id "
                    "WHERE om.user_id = :uid AND o.enforce_mfa = 1 "
                    "AND o.deleted_at IS NULL"
                ),
                {"uid": user_id},
            )
            .mappings()
            .fetchone()
        )
        return (result["cnt"] if result else 0) > 0
