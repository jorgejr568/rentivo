from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError


def _load_migration() -> ModuleType:
    path = Path(__file__).parents[1] / "alembic" / "versions" / "e0f1a2b3c4d5_add_uuid_to_billing_items.py"
    assert path.exists(), "billing item UUID migration has not been implemented"
    spec = importlib.util.spec_from_file_location("test_e0f1a2b3c4d5_add_uuid_to_billing_items", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_billing_item_uuid_migration_backfills_unique_non_null_values_and_downgrades() -> None:
    migration = _load_migration()
    assert migration.down_revision == "d9e0f1a2b3c4"
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE billing_items (id INTEGER PRIMARY KEY, billing_id INTEGER NOT NULL, "
                "description TEXT NOT NULL, amount INTEGER NOT NULL, item_type TEXT NOT NULL, "
                "sort_order INTEGER NOT NULL)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO billing_items (id, billing_id, description, amount, item_type, sort_order) VALUES "
                "(1, 10, 'Aluguel', 100, 'fixed', 0), (2, 10, 'Agua', 0, 'variable', 1)"
            )
        )
        migration.op = Operations(MigrationContext.configure(connection))

        migration.upgrade()

        columns = {column["name"]: column for column in sa.inspect(connection).get_columns("billing_items")}
        values = connection.execute(sa.text("SELECT uuid FROM billing_items ORDER BY id")).scalars().all()
        assert columns["uuid"]["nullable"] is False
        assert len(set(values)) == 2
        assert all(len(value) == 26 for value in values)
        with pytest.raises(IntegrityError):
            connection.execute(
                sa.text(
                    "INSERT INTO billing_items (id, billing_id, description, amount, item_type, sort_order, uuid) "
                    "VALUES (3, 10, 'Duplicado', 0, 'variable', 2, :uuid)"
                ),
                {"uuid": values[0]},
            )

        migration.downgrade()
        assert "uuid" not in {column["name"] for column in sa.inspect(connection).get_columns("billing_items")}
