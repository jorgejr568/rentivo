"""Migration contract for monotonic passkey usage timestamps."""

from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration() -> ModuleType:
    path = Path(__file__).parents[1] / "alembic" / "versions" / "c8d9e0f1a2b3_use_microsecond_passkey_usage.py"
    assert path.exists(), "passkey usage timestamp migration has not been implemented"
    spec = importlib.util.spec_from_file_location("test_c8d9e0f1a2b3_passkey_usage", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_passkey_usage_timestamp_migration_is_a_sqlite_noop() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")

    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE user_passkeys (last_used_at DATETIME NULL)")
        migration.op = Operations(MigrationContext.configure(connection))

        migration.upgrade()
        migration.downgrade()

        columns = sa.inspect(connection).get_columns("user_passkeys")
        assert [column["name"] for column in columns] == ["last_used_at"]


def test_passkey_usage_timestamp_migration_uses_mysql_microseconds_offline() -> None:
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
    assert "last_used_at DATETIME(6) NULL" in ddl
    assert "last_used_at DATETIME NULL" in ddl
