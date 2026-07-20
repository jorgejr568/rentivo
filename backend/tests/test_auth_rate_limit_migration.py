"""Focused verification for the shared authentication-rate-limit migration."""

from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration() -> ModuleType:
    path = Path(__file__).parents[1] / "alembic" / "versions" / "b7c8d9e0f1a2_create_auth_rate_limits.py"
    spec = importlib.util.spec_from_file_location("test_b7c8d9e0f1a2_create_auth_rate_limits", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_auth_rate_limit_migration_upgrade_and_downgrade() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = sa.inspect(connection)
        assert inspector.get_table_names() == ["auth_rate_limits"]
        columns = {column["name"] for column in inspector.get_columns("auth_rate_limits")}
        assert columns == {"action", "identity_hash", "attempts", "window_started_at", "expires_at"}
        primary_key = inspector.get_pk_constraint("auth_rate_limits")
        assert primary_key["constrained_columns"] == ["action", "identity_hash"]
        assert {index["name"] for index in inspector.get_indexes("auth_rate_limits")} == {
            "ix_auth_rate_limits_expires_at"
        }

        migration.downgrade()
        assert sa.inspect(connection).get_table_names() == []


def test_auth_rate_limit_migration_preserves_mysql_types_offline() -> None:
    migration = _load_migration()
    output = StringIO()
    migration.op = Operations(
        MigrationContext.configure(
            url="mysql+pymysql://",
            opts={"as_sql": True, "output_buffer": output},
        )
    )

    migration.upgrade()
    migration.downgrade()

    ddl = output.getvalue().replace("`", "")
    assert "identity_hash BINARY(32) NOT NULL" in ddl
    assert ddl.count("DATETIME(6)") == 2
    assert "PRIMARY KEY (action, identity_hash)" in ddl
    assert "DROP TABLE auth_rate_limits" in ddl
