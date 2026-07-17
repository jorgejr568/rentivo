"""Focused verification for the authentication-challenge migration."""

from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration() -> ModuleType:
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "a15a69fdc2d5_create_auth_challenges.py"
    spec = importlib.util.spec_from_file_location("test_a15a69fdc2d5_create_auth_challenges", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _install_operations(migration: ModuleType, connection: sa.Connection) -> None:
    context = MigrationContext.configure(connection)
    migration.op = Operations(context)


def test_auth_challenge_migration_upgrade_cascade_and_downgrade() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        metadata = sa.MetaData()
        sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
        metadata.create_all(connection)
        _install_operations(migration, connection)

        migration.upgrade()

        inspector = sa.inspect(connection)
        assert set(inspector.get_table_names()) == {"auth_challenges", "users"}
        columns = {column["name"]: column for column in inspector.get_columns("auth_challenges")}
        assert set(columns) == {
            "id",
            "uuid",
            "nonce_hash",
            "user_id",
            "phase",
            "allowed_methods",
            "webauthn_challenge",
            "failures",
            "created_at",
            "expires_at",
            "consumed_at",
        }
        assert columns["user_id"]["nullable"] is True
        indexes = {index["name"]: index for index in inspector.get_indexes("auth_challenges")}
        assert set(indexes) == {
            "ix_auth_challenges_consumed_at",
            "ix_auth_challenges_expires_at",
            "ix_auth_challenges_user_id",
            "ix_auth_challenges_uuid",
        }
        assert indexes["ix_auth_challenges_uuid"]["unique"] == 1

        foreign_keys = inspector.get_foreign_keys("auth_challenges")
        assert [(fk["constrained_columns"], fk["referred_table"]) for fk in foreign_keys] == [(["user_id"], "users")]
        assert foreign_keys[0]["options"]["ondelete"] == "CASCADE"

        connection.exec_driver_sql("INSERT INTO users (id) VALUES (7)")
        connection.exec_driver_sql(
            """
            INSERT INTO auth_challenges (
                uuid, nonce_hash, user_id, phase, allowed_methods,
                created_at, expires_at
            ) VALUES (
                '01J00000000000000000000000', zeroblob(32), 7, 'mfa',
                '["totp"]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql("DELETE FROM users WHERE id = 7")
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM auth_challenges").scalar_one() == 0

        migration.downgrade()
        assert sa.inspect(connection).get_table_names() == ["users"]


def test_auth_challenge_migration_preserves_mysql_column_types_offline() -> None:
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
    assert "nonce_hash BINARY(32) NOT NULL" in ddl
    assert "webauthn_challenge BLOB" in ddl
    assert ddl.count("DATETIME(6)") == 3
    assert "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE" in ddl
    assert "DROP TABLE auth_challenges" in ddl
