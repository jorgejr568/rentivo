"""replace uuid4 values with ulid

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-02-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from ulid import ULID

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_uuid4(value: str) -> bool:
    """Check if a string looks like a UUID4 (36 chars with hyphens)."""
    return len(value) == 36 and value.count("-") == 4


def upgrade() -> None:
    conn = op.get_bind()

    # Step 1: Collect billings that still have UUID4 values
    billing_uuid_map: dict[str, str] = {}  # old_uuid4 -> new_ulid
    for row in conn.execute(sa.text("SELECT id, uuid FROM billings")).fetchall():
        old_uuid = row[1]
        if _is_uuid4(old_uuid):
            billing_uuid_map[old_uuid] = str(ULID())

    # Step 2: Collect bills that still have UUID4 values (before any updates)
    bill_updates: list[tuple[int, str, str | None]] = []  # (id, new_ulid, new_pdf_path)
    for row in conn.execute(
        sa.text(
            "SELECT b.id, b.uuid, b.pdf_path, bi.uuid AS billing_uuid "
            "FROM bills b JOIN billings bi ON b.billing_id = bi.id"
        )
    ).fetchall():
        bill_id, old_bill_uuid, pdf_path, old_billing_uuid = row
        if not _is_uuid4(old_bill_uuid):
            continue

        new_bill_ulid = str(ULID())
        new_pdf_path = pdf_path
        if pdf_path:
            new_pdf_path = pdf_path.replace(old_bill_uuid, new_bill_ulid)
            if old_billing_uuid in billing_uuid_map:
                new_pdf_path = new_pdf_path.replace(
                    old_billing_uuid, billing_uuid_map[old_billing_uuid]
                )

        bill_updates.append((bill_id, new_bill_ulid, new_pdf_path))

    # Step 3: Apply billing UUID updates
    for old_uuid, new_ulid in billing_uuid_map.items():
        conn.execute(
            sa.text("UPDATE billings SET uuid = :new WHERE uuid = :old"),
            {"new": new_ulid, "old": old_uuid},
        )

    # Step 4: Apply bill UUID + pdf_path updates
    for bill_id, new_ulid, new_pdf_path in bill_updates:
        conn.execute(
            sa.text("UPDATE bills SET uuid = :uuid, pdf_path = :pdf_path WHERE id = :id"),
            {"uuid": new_ulid, "pdf_path": new_pdf_path, "id": bill_id},
        )

    # Step 5: Resize uuid columns from 36 to 26 chars
    with op.batch_alter_table("billings") as batch_op:
        batch_op.alter_column("uuid", existing_type=sa.String(36), type_=sa.String(26))

    with op.batch_alter_table("bills") as batch_op:
        batch_op.alter_column("uuid", existing_type=sa.String(36), type_=sa.String(26))


def downgrade() -> None:
    # Resize columns back to 36 to accommodate UUID4 format.
    # Original UUID4 values cannot be restored.
    with op.batch_alter_table("billings") as batch_op:
        batch_op.alter_column("uuid", existing_type=sa.String(26), type_=sa.String(36))

    with op.batch_alter_table("bills") as batch_op:
        batch_op.alter_column("uuid", existing_type=sa.String(26), type_=sa.String(36))
