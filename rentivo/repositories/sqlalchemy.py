from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.constants import SP_TZ
from rentivo.models.audit_log import AuditLog
from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import Billing, BillingItem, ItemType
from rentivo.models.invite import Invite
from rentivo.models.mfa import RecoveryCode, UserPasskey, UserTOTP
from rentivo.models.organization import Organization, OrganizationMember
from rentivo.models.receipt import Receipt
from rentivo.models.user import User
from rentivo.repositories.base import (
    AuditLogRepository,
    BillingRepository,
    BillRepository,
    InviteRepository,
    MFATOTPRepository,
    OrganizationRepository,
    PasskeyRepository,
    ReceiptRepository,
    RecoveryCodeRepository,
    UserRepository,
)


def _now() -> datetime:
    return datetime.now(SP_TZ)


class SQLAlchemyBillingRepository(BillingRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def create(self, billing: Billing) -> Billing:
        billing_uuid = str(ULID())
        now = _now()
        result = self.conn.execute(
            text(
                "INSERT INTO billings (name, description, pix_key, uuid, owner_type, owner_id, created_at, updated_at) "
                "VALUES (:name, :description, :pix_key, :uuid, :owner_type, :owner_id, :created_at, :updated_at)"
            ),
            {
                "name": billing.name,
                "description": billing.description,
                "pix_key": billing.pix_key,
                "uuid": billing_uuid,
                "owner_type": billing.owner_type,
                "owner_id": billing.owner_id,
                "created_at": now,
                "updated_at": now,
            },
        )
        billing_id = result.lastrowid
        for i, item in enumerate(billing.items):
            self.conn.execute(
                text(
                    "INSERT INTO billing_items (billing_id, description, amount, item_type, sort_order) "
                    "VALUES (:billing_id, :description, :amount, :item_type, :sort_order)"
                ),
                {
                    "billing_id": billing_id,
                    "description": item.description,
                    "amount": item.amount,
                    "item_type": item.item_type.value,
                    "sort_order": i,
                },
            )
        self.conn.commit()
        result = self.get_by_id(billing_id)
        if result is None:
            raise RuntimeError(f"Failed to retrieve billing after create (id={billing_id})")
        return result

    @staticmethod
    def _build_billing(row: RowMapping, item_rows: list[RowMapping]) -> Billing:
        return Billing(
            id=row["id"],
            uuid=row["uuid"],
            name=row["name"],
            description=row["description"],
            pix_key=row["pix_key"],
            owner_type=row.get("owner_type", "user"),
            owner_id=row.get("owner_id", 0),
            items=[
                BillingItem(
                    id=item_row["id"],
                    billing_id=item_row["billing_id"],
                    description=item_row["description"],
                    amount=item_row["amount"],
                    item_type=ItemType(item_row["item_type"]),
                    sort_order=item_row["sort_order"],
                )
                for item_row in item_rows
            ],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"],
        )

    def _row_to_billing(self, row: RowMapping) -> Billing:
        items = (
            self.conn.execute(
                text("SELECT * FROM billing_items WHERE billing_id = :billing_id ORDER BY sort_order"),
                {"billing_id": row["id"]},
            )
            .mappings()
            .fetchall()
        )
        return self._build_billing(row, list(items))

    def get_by_id(self, billing_id: int) -> Billing | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM billings WHERE id = :id AND deleted_at IS NULL"),
                {"id": billing_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_billing(row)

    def get_by_uuid(self, uuid: str) -> Billing | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM billings WHERE uuid = :uuid AND deleted_at IS NULL"),
                {"uuid": uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_billing(row)

    def list_all(self) -> list[Billing]:
        rows = (
            self.conn.execute(text("SELECT * FROM billings WHERE deleted_at IS NULL ORDER BY created_at DESC"))
            .mappings()
            .fetchall()
        )
        return self._build_billings_from_rows(rows)

    def list_for_user(self, user_id: int) -> list[Billing]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT * FROM billings WHERE deleted_at IS NULL AND ("
                    "(owner_type = 'user' AND owner_id = :uid) OR "
                    "(owner_type = 'organization' AND owner_id IN "
                    "(SELECT organization_id FROM organization_members WHERE user_id = :uid))"
                    ") ORDER BY created_at DESC"
                ),
                {"uid": user_id},
            )
            .mappings()
            .fetchall()
        )
        return self._build_billings_from_rows(rows)

    def _build_billings_from_rows(self, rows: list[RowMapping]) -> list[Billing]:
        if not rows:
            return []
        billing_ids = [row["id"] for row in rows]
        placeholders = ", ".join(f":id{i}" for i in range(len(billing_ids)))
        params = {f"id{i}": bid for i, bid in enumerate(billing_ids)}
        all_items = (
            self.conn.execute(
                text(f"SELECT * FROM billing_items WHERE billing_id IN ({placeholders}) ORDER BY sort_order"),
                params,
            )
            .mappings()
            .fetchall()
        )
        items_by_billing: dict[int, list[RowMapping]] = {}
        for item_row in all_items:
            items_by_billing.setdefault(item_row["billing_id"], []).append(item_row)
        return [self._build_billing(row, items_by_billing.get(row["id"], [])) for row in rows]

    def update(self, billing: Billing) -> Billing:
        self.conn.execute(
            text(
                "UPDATE billings SET name = :name, description = :description, "
                "pix_key = :pix_key, updated_at = :updated_at WHERE id = :id"
            ),
            {
                "name": billing.name,
                "description": billing.description,
                "pix_key": billing.pix_key,
                "updated_at": _now(),
                "id": billing.id,
            },
        )
        self.conn.execute(
            text("DELETE FROM billing_items WHERE billing_id = :billing_id"),
            {"billing_id": billing.id},
        )
        for i, item in enumerate(billing.items):
            self.conn.execute(
                text(
                    "INSERT INTO billing_items (billing_id, description, amount, item_type, sort_order) "
                    "VALUES (:billing_id, :description, :amount, :item_type, :sort_order)"
                ),
                {
                    "billing_id": billing.id,
                    "description": item.description,
                    "amount": item.amount,
                    "item_type": item.item_type.value,
                    "sort_order": i,
                },
            )
        self.conn.commit()
        if billing.id is None:  # pragma: no cover
            raise ValueError("Cannot update billing without an id")
        result = self.get_by_id(billing.id)
        if result is None:
            raise RuntimeError(f"Failed to retrieve billing after update (id={billing.id})")
        return result

    def delete(self, billing_id: int) -> None:
        self.conn.execute(
            text("UPDATE billings SET deleted_at = :deleted_at WHERE id = :id"),
            {"deleted_at": _now(), "id": billing_id},
        )
        self.conn.commit()

    def transfer_owner(self, billing_id: int, owner_type: str, owner_id: int) -> None:
        self.conn.execute(
            text(
                "UPDATE billings SET owner_type = :owner_type, owner_id = :owner_id, "
                "updated_at = :updated_at WHERE id = :id"
            ),
            {"owner_type": owner_type, "owner_id": owner_id, "updated_at": _now(), "id": billing_id},
        )
        self.conn.commit()


class SQLAlchemyBillRepository(BillRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def create(self, bill: Bill) -> Bill:
        bill_uuid = str(ULID())
        result = self.conn.execute(
            text(
                "INSERT INTO bills (billing_id, reference_month, total_amount, "
                "pdf_path, notes, uuid, due_date, created_at) "
                "VALUES (:billing_id, :reference_month, :total_amount, "
                ":pdf_path, :notes, :uuid, :due_date, :created_at)"
            ),
            {
                "billing_id": bill.billing_id,
                "reference_month": bill.reference_month,
                "total_amount": bill.total_amount,
                "pdf_path": bill.pdf_path,
                "notes": bill.notes,
                "uuid": bill_uuid,
                "due_date": bill.due_date,
                "created_at": _now(),
            },
        )
        bill_id = result.lastrowid
        for i, item in enumerate(bill.line_items):
            self.conn.execute(
                text(
                    "INSERT INTO bill_line_items (bill_id, description, amount, item_type, sort_order) "
                    "VALUES (:bill_id, :description, :amount, :item_type, :sort_order)"
                ),
                {
                    "bill_id": bill_id,
                    "description": item.description,
                    "amount": item.amount,
                    "item_type": item.item_type.value,
                    "sort_order": i,
                },
            )
        self.conn.commit()
        result = self.get_by_id(bill_id)
        if result is None:
            raise RuntimeError(f"Failed to retrieve bill after create (id={bill_id})")
        return result

    @staticmethod
    def _build_bill(row: RowMapping, item_rows: list[RowMapping]) -> Bill:
        return Bill(
            id=row["id"],
            uuid=row["uuid"],
            billing_id=row["billing_id"],
            reference_month=row["reference_month"],
            total_amount=row["total_amount"],
            line_items=[
                BillLineItem(
                    id=item_row["id"],
                    bill_id=item_row["bill_id"],
                    description=item_row["description"],
                    amount=item_row["amount"],
                    item_type=ItemType(item_row["item_type"]),
                    sort_order=item_row["sort_order"],
                )
                for item_row in item_rows
            ],
            pdf_path=row["pdf_path"],
            notes=row["notes"],
            due_date=row["due_date"],
            paid_at=row["paid_at"],
            created_at=row["created_at"],
            deleted_at=row["deleted_at"],
        )

    def _row_to_bill(self, row: RowMapping) -> Bill:
        items = (
            self.conn.execute(
                text("SELECT * FROM bill_line_items WHERE bill_id = :bill_id ORDER BY sort_order"),
                {"bill_id": row["id"]},
            )
            .mappings()
            .fetchall()
        )
        return self._build_bill(row, list(items))

    def get_by_id(self, bill_id: int) -> Bill | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM bills WHERE id = :id AND deleted_at IS NULL"),
                {"id": bill_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_bill(row)

    def get_by_uuid(self, uuid: str) -> Bill | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM bills WHERE uuid = :uuid AND deleted_at IS NULL"),
                {"uuid": uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_bill(row)

    def list_by_billing(self, billing_id: int) -> list[Bill]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT * FROM bills WHERE billing_id = :billing_id "
                    "AND deleted_at IS NULL ORDER BY reference_month DESC"
                ),
                {"billing_id": billing_id},
            )
            .mappings()
            .fetchall()
        )
        if not rows:
            return []
        bill_ids = [row["id"] for row in rows]
        placeholders = ", ".join(f":id{i}" for i in range(len(bill_ids)))
        params = {f"id{i}": bid for i, bid in enumerate(bill_ids)}
        all_items = (
            self.conn.execute(
                text(f"SELECT * FROM bill_line_items WHERE bill_id IN ({placeholders}) ORDER BY sort_order"),
                params,
            )
            .mappings()
            .fetchall()
        )
        items_by_bill: dict[int, list[RowMapping]] = {}
        for item_row in all_items:
            items_by_bill.setdefault(item_row["bill_id"], []).append(item_row)
        return [self._build_bill(row, items_by_bill.get(row["id"], [])) for row in rows]

    def update(self, bill: Bill) -> Bill:
        self.conn.execute(
            text(
                "UPDATE bills SET reference_month = :reference_month, "
                "total_amount = :total_amount, notes = :notes, due_date = :due_date WHERE id = :id"
            ),
            {
                "reference_month": bill.reference_month,
                "total_amount": bill.total_amount,
                "notes": bill.notes,
                "due_date": bill.due_date,
                "id": bill.id,
            },
        )
        self.conn.execute(
            text("DELETE FROM bill_line_items WHERE bill_id = :bill_id"),
            {"bill_id": bill.id},
        )
        for i, item in enumerate(bill.line_items):
            self.conn.execute(
                text(
                    "INSERT INTO bill_line_items (bill_id, description, amount, item_type, sort_order) "
                    "VALUES (:bill_id, :description, :amount, :item_type, :sort_order)"
                ),
                {
                    "bill_id": bill.id,
                    "description": item.description,
                    "amount": item.amount,
                    "item_type": item.item_type.value,
                    "sort_order": i,
                },
            )
        self.conn.commit()
        if bill.id is None:  # pragma: no cover
            raise ValueError("Cannot update bill without an id")
        result = self.get_by_id(bill.id)
        if result is None:
            raise RuntimeError(f"Failed to retrieve bill after update (id={bill.id})")
        return result

    def update_pdf_path(self, bill_id: int, pdf_path: str) -> None:
        self.conn.execute(
            text("UPDATE bills SET pdf_path = :pdf_path WHERE id = :id"),
            {"pdf_path": pdf_path, "id": bill_id},
        )
        self.conn.commit()

    def update_paid_at(self, bill_id: int, paid_at: datetime | None) -> None:
        self.conn.execute(
            text("UPDATE bills SET paid_at = :paid_at WHERE id = :id"),
            {"paid_at": paid_at, "id": bill_id},
        )
        self.conn.commit()

    def delete(self, bill_id: int) -> None:
        self.conn.execute(
            text("UPDATE bills SET deleted_at = :deleted_at WHERE id = :id"),
            {"deleted_at": _now(), "id": bill_id},
        )
        self.conn.commit()


class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row_to_user(row: RowMapping) -> User:
        return User(
            id=row["id"],
            username=row["username"],
            email=row.get("email", ""),
            password_hash=row["password_hash"],
            created_at=row["created_at"],
        )

    def create(self, user: User) -> User:
        self.conn.execute(
            text(
                "INSERT INTO users (username, email, password_hash, created_at) "
                "VALUES (:username, :email, :password_hash, :created_at)"
            ),
            {"username": user.username, "email": user.email, "password_hash": user.password_hash, "created_at": _now()},
        )
        self.conn.commit()
        result = self.get_by_username(user.username)
        if result is None:
            raise RuntimeError(f"Failed to retrieve user after create (username={user.username})")
        return result

    def get_by_id(self, user_id: int) -> User | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM users WHERE id = :id"),
                {"id": user_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_user(row)

    def get_by_username(self, username: str) -> User | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM users WHERE username = :username"),
                {"username": username},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_user(row)

    def list_all(self) -> list[User]:
        rows = self.conn.execute(text("SELECT * FROM users ORDER BY created_at DESC")).mappings().fetchall()
        return [self._row_to_user(row) for row in rows]

    def update_password_hash(self, username: str, password_hash: str) -> None:
        self.conn.execute(
            text("UPDATE users SET password_hash = :password_hash WHERE username = :username"),
            {"password_hash": password_hash, "username": username},
        )
        self.conn.commit()


class SQLAlchemyOrganizationRepository(OrganizationRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row_to_org(row: RowMapping) -> Organization:
        return Organization(
            id=row["id"],
            uuid=row["uuid"],
            name=row["name"],
            created_by=row["created_by"],
            enforce_mfa=bool(row.get("enforce_mfa", False)),
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

    def update(self, org: Organization) -> Organization:
        self.conn.execute(
            text(
                "UPDATE organizations SET name = :name, enforce_mfa = :enforce_mfa, "
                "updated_at = :updated_at WHERE id = :id"
            ),
            {"name": org.name, "enforce_mfa": org.enforce_mfa, "updated_at": _now(), "id": org.id},
        )
        self.conn.commit()
        if org.id is None:  # pragma: no cover
            raise ValueError("Cannot update org without an id")
        result = self.get_by_id(org.id)
        if result is None:
            raise RuntimeError(f"Failed to retrieve org after update (id={org.id})")
        return result

    def delete(self, org_id: int) -> None:
        self.conn.execute(
            text("UPDATE organizations SET deleted_at = :deleted_at WHERE id = :id"),
            {"deleted_at": _now(), "id": org_id},
        )
        self.conn.commit()

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

    def remove_member(self, org_id: int, user_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM organization_members WHERE organization_id = :org_id AND user_id = :user_id"),
            {"org_id": org_id, "user_id": user_id},
        )
        self.conn.commit()

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

    def list_members(self, org_id: int) -> list[OrganizationMember]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT om.*, u.username FROM organization_members om "
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
                username=row.get("username", ""),
                role=row["role"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def update_member_role(self, org_id: int, user_id: int, role: str) -> None:
        self.conn.execute(
            text("UPDATE organization_members SET role = :role WHERE organization_id = :org_id AND user_id = :user_id"),
            {"role": role, "org_id": org_id, "user_id": user_id},
        )
        self.conn.commit()

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


class SQLAlchemyInviteRepository(InviteRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row_to_invite(row: RowMapping) -> Invite:
        return Invite(
            id=row["id"],
            uuid=row["uuid"],
            organization_id=row["organization_id"],
            organization_name=row.get("org_name", ""),
            invited_user_id=row["invited_user_id"],
            invited_username=row.get("invited_username", ""),
            invited_by_user_id=row["invited_by_user_id"],
            invited_by_username=row.get("invited_by_username", ""),
            role=row["role"],
            status=row["status"],
            enforce_mfa=bool(row.get("enforce_mfa", False)),
            created_at=row["created_at"],
            responded_at=row.get("responded_at"),
        )

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

    def get_by_uuid(self, uuid: str) -> Invite | None:
        row = (
            self.conn.execute(
                text(
                    "SELECT i.*, o.name AS org_name, o.enforce_mfa, "
                    "u1.username AS invited_username, u2.username AS invited_by_username "
                    "FROM invites i "
                    "JOIN organizations o ON i.organization_id = o.id "
                    "JOIN users u1 ON i.invited_user_id = u1.id "
                    "JOIN users u2 ON i.invited_by_user_id = u2.id "
                    "WHERE i.uuid = :uuid"
                ),
                {"uuid": uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_invite(row)

    def list_pending_for_user(self, user_id: int) -> list[Invite]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT i.*, o.name AS org_name, o.enforce_mfa, "
                    "u1.username AS invited_username, u2.username AS invited_by_username "
                    "FROM invites i "
                    "JOIN organizations o ON i.organization_id = o.id "
                    "JOIN users u1 ON i.invited_user_id = u1.id "
                    "JOIN users u2 ON i.invited_by_user_id = u2.id "
                    "WHERE i.invited_user_id = :uid AND i.status = 'pending' "
                    "ORDER BY i.created_at DESC"
                ),
                {"uid": user_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_invite(row) for row in rows]

    def list_by_organization(self, org_id: int) -> list[Invite]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT i.*, o.name AS org_name, o.enforce_mfa, "
                    "u1.username AS invited_username, u2.username AS invited_by_username "
                    "FROM invites i "
                    "JOIN organizations o ON i.organization_id = o.id "
                    "JOIN users u1 ON i.invited_user_id = u1.id "
                    "JOIN users u2 ON i.invited_by_user_id = u2.id "
                    "WHERE i.organization_id = :org_id "
                    "ORDER BY i.created_at DESC"
                ),
                {"org_id": org_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_invite(row) for row in rows]

    def update_status(self, invite_id: int, status: str) -> None:
        self.conn.execute(
            text("UPDATE invites SET status = :status, responded_at = :responded_at WHERE id = :id"),
            {"status": status, "responded_at": _now(), "id": invite_id},
        )
        self.conn.commit()

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


class SQLAlchemyReceiptRepository(ReceiptRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row_to_receipt(row: RowMapping) -> Receipt:
        return Receipt(
            id=row["id"],
            uuid=row["uuid"],
            bill_id=row["bill_id"],
            filename=row["filename"],
            storage_key=row["storage_key"],
            content_type=row["content_type"],
            file_size=row["file_size"],
            sort_order=row["sort_order"],
            created_at=row["created_at"],
        )

    def create(self, receipt: Receipt) -> Receipt:
        receipt_uuid = str(ULID())
        now = _now()
        self.conn.execute(
            text(
                "INSERT INTO receipts (uuid, bill_id, filename, storage_key, content_type, "
                "file_size, sort_order, created_at) "
                "VALUES (:uuid, :bill_id, :filename, :storage_key, :content_type, "
                ":file_size, :sort_order, :created_at)"
            ),
            {
                "uuid": receipt_uuid,
                "bill_id": receipt.bill_id,
                "filename": receipt.filename,
                "storage_key": receipt.storage_key,
                "content_type": receipt.content_type,
                "file_size": receipt.file_size,
                "sort_order": receipt.sort_order,
                "created_at": now,
            },
        )
        self.conn.commit()
        created = self.get_by_uuid(receipt_uuid)
        if created is None:
            raise RuntimeError(f"Failed to retrieve receipt after create (uuid={receipt_uuid})")
        return created

    def get_by_id(self, receipt_id: int) -> Receipt | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM receipts WHERE id = :id"),
                {"id": receipt_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_receipt(row)

    def get_by_uuid(self, uuid: str) -> Receipt | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM receipts WHERE uuid = :uuid"),
                {"uuid": uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_receipt(row)

    def list_by_bill(self, bill_id: int) -> list[Receipt]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM receipts WHERE bill_id = :bill_id ORDER BY sort_order, id"),
                {"bill_id": bill_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_receipt(row) for row in rows]

    def delete(self, receipt_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        )
        self.conn.commit()


class SQLAlchemyAuditLogRepository(AuditLogRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row_to_audit_log(row: RowMapping) -> AuditLog:
        import json

        previous_state = row["previous_state"]
        if isinstance(previous_state, str):
            previous_state = json.loads(previous_state)
        new_state = row["new_state"]
        if isinstance(new_state, str):
            new_state = json.loads(new_state)
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return AuditLog(
            id=row["id"],
            uuid=row["uuid"],
            event_type=row["event_type"],
            actor_id=row["actor_id"],
            actor_username=row["actor_username"],
            source=row["source"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            entity_uuid=row["entity_uuid"],
            previous_state=previous_state,
            new_state=new_state,
            metadata=metadata,
            created_at=row["created_at"],
        )

    def create(self, audit_log: AuditLog) -> AuditLog:
        import json

        audit_uuid = str(ULID())
        now = _now()
        self.conn.execute(
            text(
                "INSERT INTO audit_logs (uuid, event_type, actor_id, actor_username, "
                "source, entity_type, entity_id, entity_uuid, previous_state, "
                "new_state, metadata, created_at) "
                "VALUES (:uuid, :event_type, :actor_id, :actor_username, "
                ":source, :entity_type, :entity_id, :entity_uuid, :previous_state, "
                ":new_state, :metadata, :created_at)"
            ),
            {
                "uuid": audit_uuid,
                "event_type": audit_log.event_type,
                "actor_id": audit_log.actor_id,
                "actor_username": audit_log.actor_username,
                "source": audit_log.source,
                "entity_type": audit_log.entity_type,
                "entity_id": audit_log.entity_id,
                "entity_uuid": audit_log.entity_uuid,
                "previous_state": json.dumps(audit_log.previous_state)
                if audit_log.previous_state is not None
                else None,
                "new_state": json.dumps(audit_log.new_state) if audit_log.new_state is not None else None,
                "metadata": json.dumps(audit_log.metadata),
                "created_at": now,
            },
        )
        self.conn.commit()

        row = (
            self.conn.execute(
                text("SELECT * FROM audit_logs WHERE uuid = :uuid"),
                {"uuid": audit_uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            raise RuntimeError(f"Failed to retrieve audit log after create (uuid={audit_uuid})")
        return self._row_to_audit_log(row)

    def list_by_entity(self, entity_type: str, entity_id: int) -> list[AuditLog]:
        rows = (
            self.conn.execute(
                text(
                    "SELECT * FROM audit_logs "
                    "WHERE entity_type = :entity_type AND entity_id = :entity_id "
                    "ORDER BY created_at DESC"
                ),
                {"entity_type": entity_type, "entity_id": entity_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_audit_log(row) for row in rows]

    def list_by_actor(self, actor_id: int, limit: int = 50) -> list[AuditLog]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM audit_logs WHERE actor_id = :actor_id ORDER BY created_at DESC LIMIT :limit"),
                {"actor_id": actor_id, "limit": limit},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_audit_log(row) for row in rows]

    def list_recent(self, limit: int = 50) -> list[AuditLog]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT :limit"),
                {"limit": limit},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_audit_log(row) for row in rows]


class SQLAlchemyMFATOTPRepository(MFATOTPRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row_to_totp(row: RowMapping) -> UserTOTP:
        return UserTOTP(
            id=row["id"],
            user_id=row["user_id"],
            secret=row["secret"],
            confirmed=bool(row["confirmed"]),
            created_at=row["created_at"],
            confirmed_at=row.get("confirmed_at"),
        )

    def get_by_user_id(self, user_id: int) -> UserTOTP | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM user_totp WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_totp(row)

    def create(self, totp: UserTOTP) -> UserTOTP:
        self.conn.execute(
            text(
                "INSERT INTO user_totp (user_id, secret, confirmed, created_at) "
                "VALUES (:user_id, :secret, :confirmed, :created_at)"
            ),
            {
                "user_id": totp.user_id,
                "secret": totp.secret,
                "confirmed": totp.confirmed,
                "created_at": _now(),
            },
        )
        self.conn.commit()
        result = self.get_by_user_id(totp.user_id)
        if result is None:
            raise RuntimeError("Failed to retrieve TOTP after create")
        return result

    def confirm(self, user_id: int) -> None:
        self.conn.execute(
            text("UPDATE user_totp SET confirmed = 1, confirmed_at = :now WHERE user_id = :user_id"),
            {"now": _now(), "user_id": user_id},
        )
        self.conn.commit()

    def delete_by_user_id(self, user_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM user_totp WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        self.conn.commit()


class SQLAlchemyRecoveryCodeRepository(RecoveryCodeRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row_to_code(row: RowMapping) -> RecoveryCode:
        return RecoveryCode(
            id=row["id"],
            user_id=row["user_id"],
            code_hash=row["code_hash"],
            used_at=row.get("used_at"),
            created_at=row["created_at"],
        )

    def create_batch(self, user_id: int, code_hashes: list[str]) -> None:
        now = _now()
        for code_hash in code_hashes:
            self.conn.execute(
                text(
                    "INSERT INTO user_recovery_codes (user_id, code_hash, created_at) "
                    "VALUES (:user_id, :code_hash, :created_at)"
                ),
                {"user_id": user_id, "code_hash": code_hash, "created_at": now},
            )
        self.conn.commit()

    def list_unused_by_user(self, user_id: int) -> list[RecoveryCode]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM user_recovery_codes WHERE user_id = :user_id AND used_at IS NULL ORDER BY id"),
                {"user_id": user_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_code(row) for row in rows]

    def mark_used(self, code_id: int) -> None:
        self.conn.execute(
            text("UPDATE user_recovery_codes SET used_at = :now WHERE id = :id"),
            {"now": _now(), "id": code_id},
        )
        self.conn.commit()

    def delete_all_by_user(self, user_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM user_recovery_codes WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        self.conn.commit()


class SQLAlchemyPasskeyRepository(PasskeyRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row_to_passkey(row: RowMapping) -> UserPasskey:
        return UserPasskey(
            id=row["id"],
            uuid=row["uuid"],
            user_id=row["user_id"],
            credential_id=row["credential_id"],
            public_key=row["public_key"],
            sign_count=row["sign_count"],
            name=row["name"],
            transports=row.get("transports"),
            created_at=row["created_at"],
            last_used_at=row.get("last_used_at"),
        )

    def create(self, passkey: UserPasskey) -> UserPasskey:
        passkey_uuid = str(ULID())
        now = _now()
        self.conn.execute(
            text(
                "INSERT INTO user_passkeys (uuid, user_id, credential_id, public_key, "
                "sign_count, name, transports, created_at) "
                "VALUES (:uuid, :user_id, :credential_id, :public_key, "
                ":sign_count, :name, :transports, :created_at)"
            ),
            {
                "uuid": passkey_uuid,
                "user_id": passkey.user_id,
                "credential_id": passkey.credential_id,
                "public_key": passkey.public_key,
                "sign_count": passkey.sign_count,
                "name": passkey.name,
                "transports": passkey.transports,
                "created_at": now,
            },
        )
        self.conn.commit()
        created = self.get_by_uuid(passkey_uuid)
        if created is None:
            raise RuntimeError("Failed to retrieve passkey after create")
        return created

    def get_by_uuid(self, uuid: str) -> UserPasskey | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM user_passkeys WHERE uuid = :uuid"),
                {"uuid": uuid},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_passkey(row)

    def get_by_credential_id(self, credential_id: str) -> UserPasskey | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM user_passkeys WHERE credential_id = :cid"),
                {"cid": credential_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_passkey(row)

    def list_by_user(self, user_id: int) -> list[UserPasskey]:
        rows = (
            self.conn.execute(
                text("SELECT * FROM user_passkeys WHERE user_id = :user_id ORDER BY created_at"),
                {"user_id": user_id},
            )
            .mappings()
            .fetchall()
        )
        return [self._row_to_passkey(row) for row in rows]

    def update_sign_count(self, passkey_id: int, sign_count: int) -> None:
        self.conn.execute(
            text("UPDATE user_passkeys SET sign_count = :sign_count WHERE id = :id"),
            {"sign_count": sign_count, "id": passkey_id},
        )
        self.conn.commit()

    def update_last_used(self, passkey_id: int) -> None:
        self.conn.execute(
            text("UPDATE user_passkeys SET last_used_at = :now WHERE id = :id"),
            {"now": _now(), "id": passkey_id},
        )
        self.conn.commit()

    def delete(self, passkey_id: int) -> None:
        self.conn.execute(
            text("DELETE FROM user_passkeys WHERE id = :id"),
            {"id": passkey_id},
        )
        self.conn.commit()
