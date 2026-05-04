from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import text


@pytest.fixture()
def seeded_db(db_connection):
    """Insert a small set of plaintext + already-encrypted rows so the
    backfill has a representative mixture to operate on."""
    user_rows = [
        {
            "e": "alice@example.com",
            "ph": "x",
            "pk": "alice@pix.com",
            "pmn": "Alice",
            "pmc": "Sao Paulo",
        },
        {
            "e": "already@example.com",
            "ph": "x",
            "pk": "fake:already-encrypted",
            "pmn": "fake:Already",
            "pmc": "fake:City",
        },
        {"e": "blank@example.com", "ph": "x", "pk": "", "pmn": "", "pmc": ""},
    ]
    for params in user_rows:
        db_connection.execute(
            text(
                "INSERT INTO users (email, password_hash, pix_key, pix_merchant_name, "
                "pix_merchant_city) VALUES (:e, :ph, :pk, :pmn, :pmc)"
            ),
            params,
        )
    billing_rows = [
        {
            "n": "B1",
            "pk": "test@pix.com",
            "pmn": "Owner",
            "pmc": "City",
            "u": "01HXBILLING01000000000000000",
            "t": "2026-04-01 00:00:00",
        },
        {
            "n": "B2",
            "pk": "fake:enc",
            "pmn": "fake:enc",
            "pmc": "fake:enc",
            "u": "01HXBILLING02000000000000000",
            "t": "2026-04-01 00:00:00",
        },
    ]
    for params in billing_rows:
        db_connection.execute(
            text(
                "INSERT INTO billings (name, description, pix_key, pix_merchant_name, "
                "pix_merchant_city, uuid, owner_type, owner_id, created_at, updated_at) "
                "VALUES (:n, '', :pk, :pmn, :pmc, :u, 'user', 0, :t, :t)"
            ),
            params,
        )
    db_connection.commit()
    return db_connection


class TestBackfillEncryption:
    def test_dry_run_does_not_write(self, seeded_db, fake_encryption, capsys):
        from rentivo.scripts import backfill_encryption

        backfill_encryption.run(seeded_db, fake_encryption, dry_run=True)

        # Verify Alice's plaintext is unchanged.
        row = (
            seeded_db.execute(
                text("SELECT pix_key FROM users WHERE email = :e"),
                {"e": "alice@example.com"},
            )
            .mappings()
            .fetchone()
        )
        assert row["pix_key"] == "alice@pix.com"  # NOT encrypted

        out = capsys.readouterr().out
        assert "dry-run" in out.lower() or "DRY-RUN" in out

    def test_run_encrypts_plaintext_rows(self, seeded_db, fake_encryption):
        from rentivo.scripts import backfill_encryption

        backfill_encryption.run(seeded_db, fake_encryption, dry_run=False)

        row = (
            seeded_db.execute(
                text("SELECT pix_key, pix_merchant_name, pix_merchant_city FROM users WHERE email = :e"),
                {"e": "alice@example.com"},
            )
            .mappings()
            .fetchone()
        )
        assert row["pix_key"] == "fake:alice@pix.com"
        assert row["pix_merchant_name"] == "fake:Alice"
        assert row["pix_merchant_city"] == "fake:Sao Paulo"

    def test_skips_already_encrypted_rows(self, seeded_db, fake_encryption):
        from rentivo.scripts import backfill_encryption

        backfill_encryption.run(seeded_db, fake_encryption, dry_run=False)

        row = (
            seeded_db.execute(
                text("SELECT pix_key FROM users WHERE email = :e"),
                {"e": "already@example.com"},
            )
            .mappings()
            .fetchone()
        )
        # Single 'fake:' prefix — not double-encrypted.
        assert row["pix_key"] == "fake:already-encrypted"

    def test_skips_empty_strings(self, seeded_db, fake_encryption):
        from rentivo.scripts import backfill_encryption

        backfill_encryption.run(seeded_db, fake_encryption, dry_run=False)

        row = (
            seeded_db.execute(
                text("SELECT pix_key FROM users WHERE email = :e"),
                {"e": "blank@example.com"},
            )
            .mappings()
            .fetchone()
        )
        assert row["pix_key"] == ""  # untouched

    def test_idempotent_second_run(self, seeded_db, fake_encryption):
        from rentivo.scripts import backfill_encryption

        backfill_encryption.run(seeded_db, fake_encryption, dry_run=False)
        backfill_encryption.run(seeded_db, fake_encryption, dry_run=False)

        row = (
            seeded_db.execute(
                text("SELECT pix_key FROM users WHERE email = :e"),
                {"e": "alice@example.com"},
            )
            .mappings()
            .fetchone()
        )
        # Still single 'fake:' prefix — not double-encrypted.
        assert row["pix_key"] == "fake:alice@pix.com"

    def test_rewrites_foreign_prefixed_rows(self, db_connection, fake_encryption):
        """Rows in another backend's format (e.g. base64 row read by a KMS-backed
        run) must be detected as not-our-ciphertext and re-written through
        encrypt(). FakeEncryptingBackend's is_encrypted only recognises 'fake:',
        so a 'b64:v1:...' row qualifies as 'needs rewrite'."""
        from sqlalchemy import text

        from rentivo.scripts import backfill_encryption

        db_connection.execute(
            text(
                "INSERT INTO users (email, password_hash, pix_key, pix_merchant_name, "
                "pix_merchant_city) VALUES (:e, :ph, :pk, :pmn, :pmc)"
            ),
            {
                "e": "transition@example.com",
                "ph": "x",
                "pk": "b64:v1:dGVzdEBwaXguY29t",
                "pmn": "",
                "pmc": "",
            },
        )
        db_connection.commit()

        backfill_encryption.run(db_connection, fake_encryption, dry_run=False)

        row = (
            db_connection.execute(
                text("SELECT pix_key FROM users WHERE email = :e"),
                {"e": "transition@example.com"},
            )
            .mappings()
            .fetchone()
        )
        # The fake backend wraps the foreign-prefix value verbatim — that's the
        # point: the operator-facing kms backfill replaces b64 rows with enc rows
        # and there is no double-encrypt risk because each backend's is_encrypted
        # only matches its own prefix.
        assert row["pix_key"] == "fake:b64:v1:dGVzdEBwaXguY29t"

    def test_encrypts_billings(self, seeded_db, fake_encryption):
        from rentivo.scripts import backfill_encryption

        backfill_encryption.run(seeded_db, fake_encryption, dry_run=False)

        row = (
            seeded_db.execute(
                text("SELECT pix_key, pix_merchant_name FROM billings WHERE uuid = :u"),
                {"u": "01HXBILLING01000000000000000"},
            )
            .mappings()
            .fetchone()
        )
        assert row["pix_key"] == "fake:test@pix.com"
        assert row["pix_merchant_name"] == "fake:Owner"

    def test_main_invokes_run_with_factories(self, seeded_db, fake_encryption):
        """Smoke test for the CLI entrypoint — factories are wired correctly."""
        from rentivo.scripts import backfill_encryption

        with (
            patch.object(backfill_encryption, "initialize_db"),
            patch.object(backfill_encryption, "get_connection", return_value=seeded_db),
            patch.object(backfill_encryption, "get_encryption", return_value=fake_encryption),
            patch("sys.argv", ["prog"]),
        ):
            backfill_encryption.main()

        # Plaintext row got encrypted.
        row = (
            seeded_db.execute(
                text("SELECT pix_key FROM users WHERE email = :e"),
                {"e": "alice@example.com"},
            )
            .mappings()
            .fetchone()
        )
        assert row["pix_key"] == "fake:alice@pix.com"


class TestBackfillEncryptionExtendedTargets:
    """Verifies the new free-text columns and receipts.filename are covered."""

    def test_billings_description_is_a_target(self):
        from rentivo.scripts.backfill_encryption import _TARGETS

        target = next(t for t in _TARGETS if t[0] == "billings")
        assert "description" in target[2]

    def test_billings_name_is_a_target(self):
        from rentivo.scripts.backfill_encryption import _TARGETS

        target = next(t for t in _TARGETS if t[0] == "billings")
        assert "name" in target[2]

    def test_billing_items_description_is_a_target(self):
        from rentivo.scripts.backfill_encryption import _TARGETS

        target = next((t for t in _TARGETS if t[0] == "billing_items"), None)
        assert target is not None
        assert target[1] == "id"
        assert target[2] == ("description",)

    def test_bills_notes_is_a_target(self):
        from rentivo.scripts.backfill_encryption import _TARGETS

        target = next((t for t in _TARGETS if t[0] == "bills"), None)
        assert target is not None
        assert "notes" in target[2]

    def test_bill_line_items_description_is_a_target(self):
        from rentivo.scripts.backfill_encryption import _TARGETS

        target = next((t for t in _TARGETS if t[0] == "bill_line_items"), None)
        assert target is not None
        assert target[2] == ("description",)

    def test_receipts_filename_is_a_target(self):
        from rentivo.scripts.backfill_encryption import _TARGETS

        target = next((t for t in _TARGETS if t[0] == "receipts"), None)
        assert target is not None
        assert target[2] == ("filename",)

    def test_backfill_rewrites_plaintext_in_new_columns(self, db_connection):
        """End-to-end: insert plaintext rows; run backfill; verify ciphertext is written."""
        from sqlalchemy import text

        from rentivo.scripts.backfill_encryption import run
        from tests.conftest import FakeEncryptingBackend

        backend = FakeEncryptingBackend()

        # Insert legacy plaintext rows directly (bypass encryption).
        db_connection.execute(
            text(
                "INSERT INTO billings (name, description, pix_key, pix_merchant_name, "
                "pix_merchant_city, uuid, owner_type, owner_id, created_at, updated_at) "
                "VALUES ('Apt 1', 'plain billing desc', '', '', '', "
                "'01HXBACK00000000000000000001', 'user', 0, "
                "'2026-04-01 00:00:00', '2026-04-01 00:00:00')"
            )
        )
        billing_id = db_connection.execute(
            text("SELECT id FROM billings WHERE uuid = '01HXBACK00000000000000000001'")
        ).scalar_one()
        db_connection.execute(
            text(
                "INSERT INTO billing_items (billing_id, description, amount, item_type, sort_order) "
                "VALUES (:bid, 'plain item', 100, 'fixed', 0)"
            ),
            {"bid": billing_id},
        )
        db_connection.execute(
            text(
                "INSERT INTO bills (billing_id, reference_month, total_amount, "
                "pdf_path, notes, uuid, due_date, status, status_updated_at, created_at) "
                "VALUES (:bid, '2025-03', 100, NULL, 'plain notes', "
                "'01HXBACK00000000000000000002', '10/04/2025', 'draft', "
                "'2026-04-01 00:00:00', '2026-04-01 00:00:00')"
            ),
            {"bid": billing_id},
        )
        bill_id = db_connection.execute(
            text("SELECT id FROM bills WHERE uuid = '01HXBACK00000000000000000002'")
        ).scalar_one()
        db_connection.execute(
            text(
                "INSERT INTO bill_line_items (bill_id, description, amount, item_type, sort_order) "
                "VALUES (:bid, 'plain bli', 100, 'fixed', 0)"
            ),
            {"bid": bill_id},
        )
        db_connection.execute(
            text(
                "INSERT INTO receipts (uuid, bill_id, filename, storage_key, content_type, "
                "file_size, sort_order, created_at) "
                "VALUES ('01HXBACK00000000000000000003', :bid, 'plain.pdf', 'k.pdf', "
                "'application/pdf', 1, 0, '2026-04-01 00:00:00')"
            ),
            {"bid": bill_id},
        )
        db_connection.commit()

        run(db_connection, backend, dry_run=False)

        # Verify each target column is now encrypted.
        billing_desc = db_connection.execute(
            text("SELECT description FROM billings WHERE id = :id"),
            {"id": billing_id},
        ).scalar_one()
        assert billing_desc == "fake:plain billing desc"

        billing_name = db_connection.execute(
            text("SELECT name FROM billings WHERE id = :id"),
            {"id": billing_id},
        ).scalar_one()
        assert billing_name == "fake:Apt 1"

        item_desc = db_connection.execute(
            text("SELECT description FROM billing_items WHERE billing_id = :id"),
            {"id": billing_id},
        ).scalar_one()
        assert item_desc == "fake:plain item"

        bill_notes = db_connection.execute(
            text("SELECT notes FROM bills WHERE id = :id"),
            {"id": bill_id},
        ).scalar_one()
        assert bill_notes == "fake:plain notes"

        bli_desc = db_connection.execute(
            text("SELECT description FROM bill_line_items WHERE bill_id = :id"),
            {"id": bill_id},
        ).scalar_one()
        assert bli_desc == "fake:plain bli"

        receipt_filename = db_connection.execute(
            text("SELECT filename FROM receipts WHERE uuid = '01HXBACK00000000000000000003'")
        ).scalar_one()
        assert receipt_filename == "fake:plain.pdf"
