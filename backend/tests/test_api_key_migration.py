"""Focused verification for the API-key persistence migration."""

from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration() -> ModuleType:
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "fe0a7b31c29d_create_api_keys.py"
    spec = importlib.util.spec_from_file_location(
        "test_fe0a7b31c29d_create_api_keys",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _install_operations(
    migration: ModuleType,
    connection: sa.Connection,
) -> None:
    context = MigrationContext.configure(connection)
    migration.op = Operations(context)


def test_api_key_migration_upgrade_cascade_and_downgrade() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        sa.MetaData().create_all(
            connection,
            tables=[
                sa.Table(
                    "users",
                    sa.MetaData(),
                    sa.Column("id", sa.Integer, primary_key=True),
                )
            ],
        )
        _install_operations(migration, connection)

        migration.upgrade()

        inspector = sa.inspect(connection)
        assert set(inspector.get_table_names()) == {
            "api_key_resource_grants",
            "api_key_scopes",
            "api_keys",
            "users",
        }

        indexes = {index["name"]: index for index in inspector.get_indexes("api_keys")}
        assert set(indexes) == {
            "ix_api_keys_expires_at",
            "ix_api_keys_revoked_at",
            "ix_api_keys_secret_hash",
            "ix_api_keys_user_id",
            "ix_api_keys_uuid",
        }
        assert indexes["ix_api_keys_uuid"]["unique"] == 1
        assert indexes["ix_api_keys_secret_hash"]["unique"] == 1

        assert inspector.get_pk_constraint("api_key_scopes")["constrained_columns"] == [
            "api_key_id",
            "scope",
        ]
        assert inspector.get_pk_constraint("api_key_resource_grants")["constrained_columns"] == [
            "api_key_id",
            "resource_type",
            "resource_id",
        ]

        api_key_fk = inspector.get_foreign_keys("api_keys")
        scope_fk = inspector.get_foreign_keys("api_key_scopes")
        grant_fk = inspector.get_foreign_keys("api_key_resource_grants")
        assert [(fk["constrained_columns"], fk["referred_table"]) for fk in api_key_fk] == [(["user_id"], "users")]
        assert [(fk["constrained_columns"], fk["referred_table"]) for fk in scope_fk] == [(["api_key_id"], "api_keys")]
        assert [(fk["constrained_columns"], fk["referred_table"]) for fk in grant_fk] == [(["api_key_id"], "api_keys")]
        assert api_key_fk[0]["options"]["ondelete"] == "CASCADE"
        assert scope_fk[0]["options"]["ondelete"] == "CASCADE"
        assert grant_fk[0]["options"]["ondelete"] == "CASCADE"

        checks = inspector.get_check_constraints("api_key_resource_grants")
        assert checks == [
            {
                "name": "ck_api_key_grant_resource_type",
                "sqltext": "resource_type IN ('user', 'organization')",
            }
        ]

        connection.exec_driver_sql("INSERT INTO users (id) VALUES (1)")
        connection.exec_driver_sql(
            """
            INSERT INTO api_keys (
                uuid, user_id, name, secret_hash, key_start, key_end,
                expires_at, created_at
            ) VALUES (
                '01J00000000000000000000000', 1, 'Browser session',
                zeroblob(32), 'aBcD', 'yZ', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
        api_key_id = connection.exec_driver_sql("SELECT id FROM api_keys").scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO api_key_scopes (api_key_id, scope) VALUES (?, ?)",
            (api_key_id, "organizations:read"),
        )
        connection.exec_driver_sql(
            """
            INSERT INTO api_key_resource_grants (
                api_key_id, resource_type, resource_id
            ) VALUES (?, ?, ?)
            """,
            (api_key_id, "organization", 42),
        )

        connection.exec_driver_sql("DELETE FROM users WHERE id = 1")
        for table_name in (
            "api_keys",
            "api_key_scopes",
            "api_key_resource_grants",
        ):
            count = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table_name}").scalar_one()
            assert count == 0

        migration.downgrade()
        assert sa.inspect(connection).get_table_names() == ["users"]


def test_api_key_migration_preserves_mysql_column_types_offline() -> None:
    migration = _load_migration()
    output = StringIO()
    context = MigrationContext.configure(
        url="mysql+pymysql://",
        opts={"as_sql": True, "output_buffer": output},
    )
    migration.op = Operations(context)

    migration.upgrade()
    migration.downgrade()

    ddl = output.getvalue().replace("`", "")
    assert "secret_hash BINARY(32) NOT NULL" in ddl
    assert ddl.count("DATETIME(6)") == 4
    assert "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE" in ddl
    assert "DROP TABLE api_key_resource_grants" in ddl
    assert "DROP TABLE api_key_scopes" in ddl
    assert "DROP TABLE api_keys" in ddl
