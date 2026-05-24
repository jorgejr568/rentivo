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

        # After backfill, email is encrypted — query by the known encrypted form.
        row = (
            seeded_db.execute(
                text("SELECT pix_key, pix_merchant_name, pix_merchant_city FROM users WHERE email = :e"),
                {"e": "fake:alice@example.com"},
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

        # After backfill, email is encrypted — query by the known encrypted form.
        row = (
            seeded_db.execute(
                text("SELECT pix_key FROM users WHERE email = :e"),
                {"e": "fake:already@example.com"},
            )
            .mappings()
            .fetchone()
        )
        # Single 'fake:' prefix — not double-encrypted.
        assert row["pix_key"] == "fake:already-encrypted"

    def test_skips_empty_strings(self, seeded_db, fake_encryption):
        from rentivo.scripts import backfill_encryption

        backfill_encryption.run(seeded_db, fake_encryption, dry_run=False)

        # After backfill, email is encrypted — query by the known encrypted form.
        row = (
            seeded_db.execute(
                text("SELECT pix_key FROM users WHERE email = :e"),
                {"e": "fake:blank@example.com"},
            )
            .mappings()
            .fetchone()
        )
        assert row["pix_key"] == ""  # untouched

    def test_idempotent_second_run(self, seeded_db, fake_encryption):
        from rentivo.scripts import backfill_encryption

        backfill_encryption.run(seeded_db, fake_encryption, dry_run=False)
        backfill_encryption.run(seeded_db, fake_encryption, dry_run=False)

        # After backfill, email is encrypted — query by the known encrypted form.
        row = (
            seeded_db.execute(
                text("SELECT pix_key FROM users WHERE email = :e"),
                {"e": "fake:alice@example.com"},
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
                {"e": "fake:transition@example.com"},
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

        # Plaintext row got encrypted — email is also now encrypted.
        row = (
            seeded_db.execute(
                text("SELECT pix_key FROM users WHERE email = :e"),
                {"e": "fake:alice@example.com"},
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


class TestBackfillUsersEmail:
    def test_backfill_encrypts_email_and_populates_hash(self, db_connection, monkeypatch):
        from sqlalchemy import text

        import rentivo.blind_index
        from rentivo.scripts.backfill_encryption import run
        from tests.conftest import FakeEncryptingBackend

        monkeypatch.setattr(rentivo.blind_index, "_cached_key", b"\x06" * 32)

        db_connection.execute(
            text(
                "INSERT INTO users (email, email_hash, password_hash, created_at) "
                "VALUES ('legacy@example.com', NULL, 'x', '2026-04-01 00:00:00')"
            )
        )
        db_connection.execute(
            text(
                "INSERT INTO users (email, email_hash, password_hash, created_at) "
                "VALUES ('OTHER@example.com', NULL, 'x', '2026-04-01 00:00:00')"
            )
        )
        db_connection.commit()

        backend = FakeEncryptingBackend()
        run(db_connection, backend, dry_run=False)

        rows = db_connection.execute(text("SELECT email, email_hash FROM users ORDER BY id")).mappings().fetchall()
        assert rows[0]["email"] == "fake:legacy@example.com"
        assert rows[1]["email"] == "fake:OTHER@example.com"
        from rentivo.blind_index import compute_email_hash

        assert rows[0]["email_hash"] == compute_email_hash("legacy@example.com")
        # Case-insensitive: the normalized form drives the hash.
        assert rows[1]["email_hash"] == compute_email_hash("other@example.com")

    def test_backfill_is_idempotent(self, db_connection, monkeypatch):
        from sqlalchemy import text

        import rentivo.blind_index
        from rentivo.scripts.backfill_encryption import run
        from tests.conftest import FakeEncryptingBackend

        monkeypatch.setattr(rentivo.blind_index, "_cached_key", b"\x07" * 32)

        db_connection.execute(
            text(
                "INSERT INTO users (email, email_hash, password_hash, created_at) "
                "VALUES ('legacy@example.com', NULL, 'x', '2026-04-01 00:00:00')"
            )
        )
        db_connection.commit()

        backend = FakeEncryptingBackend()
        run(db_connection, backend, dry_run=False)
        first = db_connection.execute(text("SELECT email, email_hash FROM users")).mappings().fetchone()

        # A second run must not double-encrypt — is_encrypted("fake:...") is True.
        run(db_connection, backend, dry_run=False)
        second = db_connection.execute(text("SELECT email, email_hash FROM users")).mappings().fetchone()
        assert first["email"] == second["email"]
        assert first["email_hash"] == second["email_hash"]

    def test_dry_run_writes_nothing(self, db_connection, monkeypatch):
        from sqlalchemy import text

        import rentivo.blind_index
        from rentivo.scripts.backfill_encryption import run
        from tests.conftest import FakeEncryptingBackend

        monkeypatch.setattr(rentivo.blind_index, "_cached_key", b"\x08" * 32)

        db_connection.execute(
            text(
                "INSERT INTO users (email, email_hash, password_hash, created_at) "
                "VALUES ('legacy@example.com', NULL, 'x', '2026-04-01 00:00:00')"
            )
        )
        db_connection.commit()

        backend = FakeEncryptingBackend()
        run(db_connection, backend, dry_run=True)
        # Dry-run does not write; email stays plaintext and hash stays NULL —
        # querying plaintext here is intentional, not a copy-paste from the
        # live-run tests above.
        row = db_connection.execute(text("SELECT email, email_hash FROM users")).mappings().fetchone()
        assert row["email"] == "legacy@example.com"
        assert row["email_hash"] is None

    def test_half_migrated_row_only_writes_hash(self, db_connection, monkeypatch):
        """Encrypted email + NULL hash → UPDATE only email_hash, leave email blob untouched."""
        from sqlalchemy import text

        import rentivo.blind_index
        from rentivo.scripts.backfill_encryption import run
        from tests.conftest import FakeEncryptingBackend

        monkeypatch.setattr(rentivo.blind_index, "_cached_key", b"\x09" * 32)

        # Seed a row where email is already ciphertext but hash is NULL.
        db_connection.execute(
            text(
                "INSERT INTO users (email, email_hash, password_hash, created_at) "
                "VALUES ('fake:legacy@example.com', NULL, 'x', '2026-04-01 00:00:00')"
            )
        )
        db_connection.commit()

        backend = FakeEncryptingBackend()
        run(db_connection, backend, dry_run=False)

        row = db_connection.execute(text("SELECT email, email_hash FROM users")).mappings().fetchone()
        # Email blob is unchanged.
        assert row["email"] == "fake:legacy@example.com"
        # Hash is populated.
        from rentivo.blind_index import compute_email_hash

        assert row["email_hash"] == compute_email_hash("legacy@example.com")

    def test_reset_blind_index_nulls_all_hashes(self, db_connection, monkeypatch):
        """--reset-blind-index NULLs every users.email_hash so the backfill re-populates them.

        Without this step, a key rotation leaves every user locked out.
        """
        from sqlalchemy import text

        import rentivo.blind_index
        from rentivo.scripts.backfill_encryption import _reset_email_hash, run
        from tests.conftest import FakeEncryptingBackend

        monkeypatch.setattr(rentivo.blind_index, "_cached_key", b"\x0a" * 32)

        # Seed a fully-migrated row (encrypted email + a stale hash).
        db_connection.execute(
            text(
                "INSERT INTO users (email, email_hash, password_hash, created_at) "
                "VALUES ('fake:user@example.com', 'STALEHASH', 'x', '2026-04-01 00:00:00')"
            )
        )
        db_connection.commit()

        _reset_email_hash(db_connection, dry_run=False)

        row = db_connection.execute(text("SELECT email_hash FROM users")).mappings().fetchone()
        assert row["email_hash"] is None

        # Subsequent backfill repopulates the hash under the current key.
        run(db_connection, FakeEncryptingBackend(), dry_run=False)
        from rentivo.blind_index import compute_email_hash

        row = db_connection.execute(text("SELECT email_hash FROM users")).mappings().fetchone()
        assert row["email_hash"] == compute_email_hash("user@example.com")

    def test_reset_blind_index_dry_run_writes_nothing(self, db_connection):
        """--reset-blind-index --dry-run prints the count but leaves hashes unchanged."""
        from sqlalchemy import text

        from rentivo.scripts.backfill_encryption import _reset_email_hash

        db_connection.execute(
            text(
                "INSERT INTO users (email, email_hash, password_hash, created_at) "
                "VALUES ('fake:user@example.com', 'STALEHASH', 'x', '2026-04-01 00:00:00')"
            )
        )
        db_connection.commit()

        _reset_email_hash(db_connection, dry_run=True)

        row = db_connection.execute(text("SELECT email_hash FROM users")).mappings().fetchone()
        assert row["email_hash"] == "STALEHASH"  # unchanged

    def test_empty_email_row_is_skipped(self, db_connection, monkeypatch):
        """Rows with an empty email string short-circuit the helper without writing.

        The column is NOT NULL but defaults to '' in some legacy fixtures; the
        skip branch keeps the backfill from generating a hash for an empty value.
        """
        from sqlalchemy import text

        import rentivo.blind_index
        from rentivo.scripts.backfill_encryption import _backfill_users_email
        from tests.conftest import FakeEncryptingBackend

        monkeypatch.setattr(rentivo.blind_index, "_cached_key", b"\x0b" * 32)

        db_connection.execute(
            text(
                "INSERT INTO users (email, email_hash, password_hash, created_at) "
                "VALUES ('', NULL, 'x', '2026-04-01 00:00:00')"
            )
        )
        db_connection.commit()

        rewritten, skipped = _backfill_users_email(db_connection, FakeEncryptingBackend(), dry_run=False)

        assert rewritten == 0
        assert skipped == 1
        row = db_connection.execute(text("SELECT email, email_hash FROM users")).mappings().fetchone()
        assert row["email"] == ""
        assert row["email_hash"] is None

    def test_main_with_reset_blind_index_flag_runs_reset(self, db_connection, monkeypatch):
        """`python -m ... --reset-blind-index` clears hashes before re-running the backfill."""
        from unittest.mock import patch

        from sqlalchemy import text

        import rentivo.blind_index
        from rentivo.scripts import backfill_encryption
        from tests.conftest import FakeEncryptingBackend

        monkeypatch.setattr(rentivo.blind_index, "_cached_key", b"\x0c" * 32)

        db_connection.execute(
            text(
                "INSERT INTO users (email, email_hash, password_hash, created_at) "
                "VALUES ('fake:user@example.com', 'STALEHASH', 'x', '2026-04-01 00:00:00')"
            )
        )
        db_connection.commit()

        with (
            patch.object(backfill_encryption, "initialize_db"),
            patch.object(backfill_encryption, "get_connection", return_value=db_connection),
            patch.object(backfill_encryption, "get_encryption", return_value=FakeEncryptingBackend()),
            patch("sys.argv", ["prog", "--reset-blind-index"]),
        ):
            backfill_encryption.main()

        from rentivo.blind_index import compute_email_hash

        row = db_connection.execute(text("SELECT email_hash FROM users")).mappings().fetchone()
        # Stale hash was wiped, then re-populated under the current key.
        assert row["email_hash"] == compute_email_hash("user@example.com")
