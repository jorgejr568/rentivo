from unittest.mock import patch

import pytest

from rentivo.models.billing import BillingItem, ItemType
from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository


class TestBillingRepoCRUD:
    def test_create_and_get(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        billing = sample_billing()
        created = billing_repo.create(billing)

        assert created.id is not None
        assert created.uuid != ""
        assert created.name == "Apt 101"
        assert len(created.items) == 2
        assert created.created_at is not None

    def test_get_by_id(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        created = billing_repo.create(sample_billing())
        fetched = billing_repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == created.name

    def test_get_by_id_not_found(self, billing_repo: SQLAlchemyBillingRepository):
        assert billing_repo.get_by_id(9999) is None

    def test_get_by_uuid(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        created = billing_repo.create(sample_billing())
        fetched = billing_repo.get_by_uuid(created.uuid)

        assert fetched is not None
        assert fetched.uuid == created.uuid

    def test_get_by_uuid_not_found(self, billing_repo: SQLAlchemyBillingRepository):
        assert billing_repo.get_by_uuid("nonexistent") is None

    def test_list_all(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        billing_repo.create(sample_billing(name="Apt 101"))
        billing_repo.create(sample_billing(name="Apt 102"))

        billings = billing_repo.list_all()
        assert len(billings) == 2

    def test_list_all_empty(self, billing_repo: SQLAlchemyBillingRepository):
        assert billing_repo.list_all() == []

    def test_list_all_with_multiple_billings_loads_items(
        self, billing_repo: SQLAlchemyBillingRepository, sample_billing
    ):
        """Bulk-load (IN-query) path: list_all() must hydrate items for every billing."""
        billing_repo.create(sample_billing(name="Apt 101"))
        billing_repo.create(sample_billing(name="Apt 102"))
        billing_repo.create(sample_billing(name="Apt 103"))

        billings = billing_repo.list_all()

        assert len(billings) == 3
        for billing in billings:
            assert len(billing.items) == 2
            assert all(isinstance(item, BillingItem) for item in billing.items)
            assert {item.item_type for item in billing.items} == {ItemType.FIXED, ItemType.VARIABLE}

    def test_list_all_returns_items(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        billing_repo.create(sample_billing())
        billings = billing_repo.list_all()
        assert len(billings[0].items) == 2

    def test_update(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        created = billing_repo.create(sample_billing())
        created.name = "Apt 102 Updated"
        created.items = [
            BillingItem(description="New item", amount=50000, item_type=ItemType.FIXED),
        ]
        updated = billing_repo.update(created)

        assert updated.name == "Apt 102 Updated"
        assert len(updated.items) == 1
        assert updated.items[0].description == "New item"

    def test_soft_delete(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        created = billing_repo.create(sample_billing())
        billing_repo.delete(created.id)

        assert billing_repo.get_by_id(created.id) is None
        assert billing_repo.list_all() == []

    def test_soft_delete_hides_from_uuid_lookup(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        created = billing_repo.create(sample_billing())
        billing_repo.delete(created.id)
        assert billing_repo.get_by_uuid(created.uuid) is None


class TestBillingRepoEdgeCases:
    def test_create_runtime_error(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        with patch.object(billing_repo, "get_by_id", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve billing after create"):
                billing_repo.create(sample_billing())

    def test_update_runtime_error(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        created = billing_repo.create(sample_billing())
        created.name = "Updated"
        with patch.object(billing_repo, "get_by_id", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve billing after update"):
                billing_repo.update(created)


class TestBillingRepoEncryption:
    """Verifies that the repository routes PIX columns through the encryption backend."""

    def test_create_encrypts_pix_columns_in_db(self, db_connection, fake_encryption, sample_billing):
        from sqlalchemy import text

        from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository

        repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
        billing = sample_billing(
            pix_key="test@pix.com",
            pix_merchant_name="John Doe",
            pix_merchant_city="Sao Paulo",
        )
        created = repo.create(billing)

        # Read raw row directly — bypass the repo's decrypt path.
        row = (
            db_connection.execute(
                text("SELECT pix_key, pix_merchant_name, pix_merchant_city FROM billings WHERE id = :id"),
                {"id": created.id},
            )
            .mappings()
            .fetchone()
        )
        assert row["pix_key"] == "fake:test@pix.com"
        assert row["pix_merchant_name"] == "fake:John Doe"
        assert row["pix_merchant_city"] == "fake:Sao Paulo"

    def test_get_decrypts_pix_columns(self, db_connection, fake_encryption, sample_billing):
        from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository

        repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
        created = repo.create(
            sample_billing(
                pix_key="test@pix.com",
                pix_merchant_name="John Doe",
                pix_merchant_city="Sao Paulo",
            )
        )
        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.pix_key == "test@pix.com"
        assert fetched.pix_merchant_name == "John Doe"
        assert fetched.pix_merchant_city == "Sao Paulo"

    def test_update_re_encrypts_pix(self, db_connection, fake_encryption, sample_billing):
        from sqlalchemy import text

        from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository

        repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
        created = repo.create(sample_billing(pix_key="old@pix.com"))
        created.pix_key = "new@pix.com"
        repo.update(created)

        row = (
            db_connection.execute(
                text("SELECT pix_key FROM billings WHERE id = :id"),
                {"id": created.id},
            )
            .mappings()
            .fetchone()
        )
        assert row["pix_key"] == "fake:new@pix.com"

    def test_get_handles_legacy_plaintext_rows(self, db_connection, fake_encryption):
        """Rows written before encryption was enabled must still be readable."""
        from sqlalchemy import text

        from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository

        # Insert a plaintext row directly (simulates a pre-backfill row).
        db_connection.execute(
            text(
                "INSERT INTO billings (name, description, pix_key, pix_merchant_name, "
                "pix_merchant_city, uuid, owner_type, owner_id, created_at, updated_at) "
                "VALUES (:name, :description, :pix_key, :pix_merchant_name, "
                ":pix_merchant_city, :uuid, :owner_type, :owner_id, :created_at, :updated_at)"
            ),
            {
                "name": "Apt 999",
                "description": "",
                "pix_key": "legacy@pix.com",
                "pix_merchant_name": "Legacy Name",
                "pix_merchant_city": "Legacy City",
                "uuid": "01HXLEGACY00000000000000000",
                "owner_type": "user",
                "owner_id": 0,
                "created_at": "2026-04-01 00:00:00",
                "updated_at": "2026-04-01 00:00:00",
            },
        )
        db_connection.commit()

        repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
        billings = repo.list_all()
        assert len(billings) == 1
        assert billings[0].pix_key == "legacy@pix.com"  # passthrough
        assert billings[0].pix_merchant_name == "Legacy Name"

    def test_create_encrypts_billing_description_and_items(self, db_connection, fake_encryption, sample_billing):
        from sqlalchemy import text

        from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository

        repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
        billing = sample_billing(description="Apt 101 - Rua Augusta")
        # Items have descriptions "Aluguel" / "Água" by default.
        created = repo.create(billing)

        row = (
            db_connection.execute(
                text("SELECT description FROM billings WHERE id = :id"),
                {"id": created.id},
            )
            .mappings()
            .fetchone()
        )
        assert row["description"] == "fake:Apt 101 - Rua Augusta"

        item_rows = (
            db_connection.execute(
                text("SELECT description FROM billing_items WHERE billing_id = :id ORDER BY sort_order"),
                {"id": created.id},
            )
            .mappings()
            .fetchall()
        )
        assert [r["description"] for r in item_rows] == ["fake:Aluguel", "fake:Água"]

    def test_get_decrypts_billing_description_and_items(self, db_connection, fake_encryption, sample_billing):
        from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository

        repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
        created = repo.create(sample_billing(description="Apt 101 - Rua Augusta"))

        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.description == "Apt 101 - Rua Augusta"
        assert [item.description for item in fetched.items] == ["Aluguel", "Água"]

    def test_update_re_encrypts_billing_description_and_items(self, db_connection, fake_encryption, sample_billing):
        from sqlalchemy import text

        from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository

        repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
        created = repo.create(sample_billing(description="old desc"))
        created.description = "new desc"
        created.items[0].description = "Aluguel atualizado"
        repo.update(created)

        row = (
            db_connection.execute(
                text("SELECT description FROM billings WHERE id = :id"),
                {"id": created.id},
            )
            .mappings()
            .fetchone()
        )
        assert row["description"] == "fake:new desc"

        item_rows = (
            db_connection.execute(
                text("SELECT description FROM billing_items WHERE billing_id = :id ORDER BY sort_order"),
                {"id": created.id},
            )
            .mappings()
            .fetchall()
        )
        assert item_rows[0]["description"] == "fake:Aluguel atualizado"

    def test_get_handles_legacy_plaintext_description(self, db_connection, fake_encryption):
        """Pre-encryption rows must read back plaintext via the no-op decrypt path."""
        from sqlalchemy import text

        from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository

        db_connection.execute(
            text(
                "INSERT INTO billings (name, description, pix_key, pix_merchant_name, "
                "pix_merchant_city, uuid, owner_type, owner_id, created_at, updated_at) "
                "VALUES ('Apt 999', 'legacy plaintext desc', '', '', '', "
                "'01HXLEGACYDESC0000000000000', 'user', 0, "
                "'2026-04-01 00:00:00', '2026-04-01 00:00:00')"
            )
        )
        billing_id = db_connection.execute(
            text("SELECT id FROM billings WHERE uuid = '01HXLEGACYDESC0000000000000'")
        ).scalar_one()
        db_connection.execute(
            text(
                "INSERT INTO billing_items (billing_id, description, amount, item_type, sort_order) "
                "VALUES (:bid, 'legacy item plaintext', 100, 'fixed', 0)"
            ),
            {"bid": billing_id},
        )
        db_connection.commit()

        repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
        fetched = repo.get_by_id(billing_id)
        assert fetched is not None
        assert fetched.description == "legacy plaintext desc"
        assert fetched.items[0].description == "legacy item plaintext"
