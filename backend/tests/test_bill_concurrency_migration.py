"""Focused contracts for bill render ownership and status timestamp precision."""

from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration() -> ModuleType:
    path = Path(__file__).parents[1] / "alembic" / "versions" / "d9e0f1a2b3c4_add_bill_concurrency_tokens.py"
    assert path.exists(), "bill concurrency migration has not been implemented"
    spec = importlib.util.spec_from_file_location("test_d9e0f1a2b3c4_bill_concurrency", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_bill_concurrency_migration_sqlite_upgrade_and_downgrade() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")

    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE bills (id INTEGER PRIMARY KEY, status_updated_at DATETIME NULL)")
        migration.op = Operations(MigrationContext.configure(connection))

        migration.upgrade()
        upgraded = {column["name"]: column for column in sa.inspect(connection).get_columns("bills")}
        assert set(upgraded) == {
            "id",
            "status_updated_at",
            "pdf_render_operation_id",
            "mutation_revision",
        }
        assert upgraded["pdf_render_operation_id"]["nullable"] is True
        assert upgraded["pdf_render_operation_id"]["type"].length == 26
        assert upgraded["mutation_revision"]["nullable"] is False
        assert upgraded["mutation_revision"]["default"] == "0"

        migration.downgrade()
        assert [column["name"] for column in sa.inspect(connection).get_columns("bills")] == [
            "id",
            "status_updated_at",
        ]


def test_bill_concurrency_migration_uses_mariadb_microseconds_offline() -> None:
    migration = _load_migration()
    output = StringIO()
    migration.op = Operations(
        MigrationContext.configure(
            url="mariadb+pymysql://",
            opts={"as_sql": True, "output_buffer": output},
        )
    )

    migration.upgrade()
    migration.downgrade()

    ddl = output.getvalue().replace("`", "")
    assert "ADD COLUMN pdf_render_operation_id VARCHAR(26)" in ddl
    assert "ADD COLUMN mutation_revision INTEGER" in ddl
    assert "DEFAULT 0" in ddl
    assert "status_updated_at DATETIME(6) NULL" in ddl
    assert "status_updated_at DATETIME NULL" in ddl
    assert "DROP COLUMN pdf_render_operation_id" in ddl
    assert "DROP COLUMN mutation_revision" in ddl
