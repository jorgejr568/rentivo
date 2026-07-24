"""Focused verification for the user foreign-key relaxation migration."""

from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration() -> ModuleType:
    path = Path(__file__).parents[1] / "alembic" / "versions" / "6f876ec79535_relax_user_fks_for_account_deletion.py"
    assert path.exists(), "user FK relaxation migration has not been implemented"
    spec = importlib.util.spec_from_file_location("test_6f876ec79535_relax_user_fks", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _render_offline(migration: ModuleType, direction: str) -> str:
    output = StringIO()
    migration.op = Operations(
        MigrationContext.configure(
            url="mysql+pymysql://",
            opts={"as_sql": True, "output_buffer": output},
        )
    )
    getattr(migration, direction)()
    return output.getvalue().replace("`", "")


def test_relax_user_fks_migration_revision_chain() -> None:
    migration = _load_migration()
    assert migration.revision == "6f876ec79535"
    assert migration.down_revision == "e0f1a2b3c4d5"


def test_relax_user_fks_migration_upgrade_relaxes_constraints_offline() -> None:
    migration = _load_migration()

    ddl = _render_offline(migration, "upgrade")

    # organizations.created_by becomes nullable and its FK re-created with ON DELETE SET NULL.
    assert "ALTER TABLE organizations DROP FOREIGN KEY organizations_ibfk_1" in ddl
    assert "ALTER TABLE organizations MODIFY created_by INTEGER NULL" in ddl
    assert (
        "ALTER TABLE organizations ADD CONSTRAINT organizations_ibfk_1 "
        "FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL" in ddl
    )
    # invites FK re-created with ON DELETE CASCADE.
    assert "ALTER TABLE invites DROP FOREIGN KEY invites_ibfk_3" in ddl
    assert (
        "ALTER TABLE invites ADD CONSTRAINT invites_ibfk_3 "
        "FOREIGN KEY(invited_by_user_id) REFERENCES users (id) ON DELETE CASCADE" in ddl
    )


def test_relax_user_fks_migration_downgrade_restores_constraints_offline() -> None:
    migration = _load_migration()

    ddl = _render_offline(migration, "downgrade")

    # invites FK restored without any ON DELETE action.
    assert "ALTER TABLE invites DROP FOREIGN KEY invites_ibfk_3" in ddl
    assert (
        "ALTER TABLE invites ADD CONSTRAINT invites_ibfk_3 "
        "FOREIGN KEY(invited_by_user_id) REFERENCES users (id);" in ddl
    )
    # organizations.created_by becomes NOT NULL again with a plain FK.
    assert "ALTER TABLE organizations DROP FOREIGN KEY organizations_ibfk_1" in ddl
    assert "ALTER TABLE organizations MODIFY created_by INTEGER NOT NULL" in ddl
    assert (
        "ALTER TABLE organizations ADD CONSTRAINT organizations_ibfk_1 "
        "FOREIGN KEY(created_by) REFERENCES users (id);" in ddl
    )
    # The relaxed referential actions are fully reverted.
    assert "ON DELETE SET NULL" not in ddl
    assert "ON DELETE CASCADE" not in ddl
