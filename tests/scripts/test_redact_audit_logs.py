"""Tests for the audit-log PII redaction backfill script."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

_TEST_SECRET = "test-hmac-secret"


@pytest.fixture()
def seeded_audit_db(db_connection):
    """Insert a representative mix of audit_logs rows with plaintext PIX."""
    rows = [
        {
            "uuid": "01HXAUDIT0000000000000000A1",
            "event_type": "billing.update",
            "actor_id": 1,
            "actor_username": "alice@example.com",
            "source": "web",
            "entity_type": "billing",
            "entity_id": 1,
            "entity_uuid": "01HXBILLING0000000000000001",
            "previous_state": json.dumps(
                {
                    "id": 1,
                    "name": "Apt 101",
                    "pix_key": "alice@pix.com",
                    "pix_merchant_name": "Alice",
                    "pix_merchant_city": "Sao Paulo",
                    "owner_id": 5,
                }
            ),
            "new_state": json.dumps(
                {
                    "id": 1,
                    "name": "Apt 101 (renamed)",
                    "pix_key": "alice@pix.com",
                    "pix_merchant_name": "Alice",
                    "pix_merchant_city": "Sao Paulo",
                    "owner_id": 5,
                }
            ),
            "metadata": "{}",
            "created_at": "2026-04-01 00:00:00",
        },
        {
            "uuid": "01HXAUDIT0000000000000000A2",
            "event_type": "user.update",
            "actor_id": 1,
            "actor_username": "alice@example.com",
            "source": "web",
            "entity_type": "user",
            "entity_id": 5,
            "entity_uuid": "",
            "previous_state": json.dumps({"id": 5, "email": "alice@example.com"}),
            "new_state": json.dumps(
                {
                    "id": 5,
                    "email": "alice@example.com",
                    "pix_key": "alice@pix.com",
                    "pix_merchant_name": "Alice",
                    "pix_merchant_city": "Sao Paulo",
                }
            ),
            "metadata": "{}",
            "created_at": "2026-04-02 00:00:00",
        },
        {
            "uuid": "01HXAUDIT0000000000000000A3",
            "event_type": "user.login",
            "actor_id": 1,
            "actor_username": "alice@example.com",
            "source": "web",
            "entity_type": "user",
            "entity_id": 5,
            "entity_uuid": "",
            "previous_state": None,
            "new_state": None,
            "metadata": "{}",
            "created_at": "2026-04-03 00:00:00",
        },
        {
            # Already redacted (presence-boolean format) — must be skipped.
            "uuid": "01HXAUDIT0000000000000000A4",
            "event_type": "billing.update",
            "actor_id": 1,
            "actor_username": "alice@example.com",
            "source": "web",
            "entity_type": "billing",
            "entity_id": 2,
            "entity_uuid": "01HXBILLING0000000000000002",
            "previous_state": json.dumps({"id": 2, "name": "Apt 202", "pix_key_set": True}),
            "new_state": json.dumps({"id": 2, "name": "Apt 202 v2", "pix_key_set": True}),
            "metadata": "{}",
            "created_at": "2026-04-04 00:00:00",
        },
        {
            "uuid": "01HXAUDIT0000000000000000A5",
            "event_type": "job.enqueued",
            "actor_id": 1,
            "actor_username": "alice@example.com",
            "source": "web",
            "entity_type": "job",
            "entity_id": 99,
            "entity_uuid": "01HXJOB0000000000000000005",
            "previous_state": None,
            "new_state": json.dumps(
                {
                    "event": "welcome",
                    "to_email": "alice@example.com",
                    "ctx_keys_count": 2,
                }
            ),
            "metadata": "{}",
            "created_at": "2026-04-05 00:00:00",
        },
    ]
    for row in rows:
        db_connection.execute(
            text(
                "INSERT INTO audit_logs (uuid, event_type, actor_id, actor_username, "
                "source, entity_type, entity_id, entity_uuid, previous_state, new_state, "
                "metadata, created_at) VALUES (:uuid, :event_type, :actor_id, "
                ":actor_username, :source, :entity_type, :entity_id, :entity_uuid, "
                ":previous_state, :new_state, :metadata, :created_at)"
            ),
            row,
        )
    db_connection.commit()
    return db_connection


class TestRedactAuditLogs:
    def test_dry_run_does_not_write(self, seeded_audit_db, capsys):
        from rentivo.scripts import redact_audit_logs

        redact_audit_logs.run(seeded_audit_db, dry_run=True, secret_key=_TEST_SECRET)

        # Plaintext is still in the DB.
        row = (
            seeded_audit_db.execute(
                text("SELECT new_state FROM audit_logs WHERE uuid = :u"),
                {"u": "01HXAUDIT0000000000000000A2"},
            )
            .mappings()
            .fetchone()
        )
        state = json.loads(row["new_state"])
        assert state["pix_key"] == "alice@pix.com"  # NOT redacted yet

        out = capsys.readouterr().out
        assert "dry-run" in out.lower() or "DRY-RUN" in out

    def test_run_redacts_billing_state(self, seeded_audit_db):
        from rentivo.scripts import redact_audit_logs

        redact_audit_logs.run(seeded_audit_db, dry_run=False, secret_key=_TEST_SECRET)

        row = (
            seeded_audit_db.execute(
                text("SELECT previous_state, new_state FROM audit_logs WHERE uuid = :u"),
                {"u": "01HXAUDIT0000000000000000A1"},
            )
            .mappings()
            .fetchone()
        )

        prev = json.loads(row["previous_state"])
        new = json.loads(row["new_state"])

        # Plaintext PIX must be gone from both states.
        for state in (prev, new):
            for key in ("pix_key", "pix_merchant_name", "pix_merchant_city"):
                assert key not in state
            assert state["pix_key_set"] is True
            assert state["pix_merchant_name_set"] is True
            assert state["pix_merchant_city_set"] is True

        # Non-PIX fields are preserved untouched.
        assert prev["id"] == 1
        assert prev["name"] == "Apt 101"
        assert new["name"] == "Apt 101 (renamed)"
        assert prev["owner_id"] == 5

    def test_run_redacts_user_new_state(self, seeded_audit_db):
        from rentivo.scripts import redact_audit_logs

        redact_audit_logs.run(seeded_audit_db, dry_run=False, secret_key=_TEST_SECRET)

        row = (
            seeded_audit_db.execute(
                text("SELECT new_state FROM audit_logs WHERE uuid = :u"),
                {"u": "01HXAUDIT0000000000000000A2"},
            )
            .mappings()
            .fetchone()
        )

        state = json.loads(row["new_state"])
        for key in ("pix_key", "pix_merchant_name", "pix_merchant_city"):
            assert key not in state
        assert state["pix_key_set"] is True
        assert state["email"] == "alice@example.com"  # email untouched

    def test_run_handles_null_states(self, seeded_audit_db):
        """Login events have null previous_state and new_state. Must not crash."""
        from rentivo.scripts import redact_audit_logs

        redact_audit_logs.run(seeded_audit_db, dry_run=False, secret_key=_TEST_SECRET)

        row = (
            seeded_audit_db.execute(
                text("SELECT previous_state, new_state FROM audit_logs WHERE uuid = :u"),
                {"u": "01HXAUDIT0000000000000000A3"},
            )
            .mappings()
            .fetchone()
        )

        assert row["previous_state"] is None
        assert row["new_state"] is None

    def test_idempotent_second_run(self, seeded_audit_db):
        from rentivo.scripts import redact_audit_logs

        redact_audit_logs.run(seeded_audit_db, dry_run=False, secret_key=_TEST_SECRET)
        redact_audit_logs.run(seeded_audit_db, dry_run=False, secret_key=_TEST_SECRET)

        row = (
            seeded_audit_db.execute(
                text("SELECT new_state FROM audit_logs WHERE uuid = :u"),
                {"u": "01HXAUDIT0000000000000000A1"},
            )
            .mappings()
            .fetchone()
        )

        state = json.loads(row["new_state"])
        assert state["pix_key_set"] is True
        # Still no plaintext key.
        assert "pix_key" not in state

    def test_skips_already_redacted_row(self, seeded_audit_db):
        """A row whose JSON already uses presence booleans is left untouched."""
        from rentivo.scripts import redact_audit_logs

        # Snapshot of the already-redacted row before run.
        row_before = (
            seeded_audit_db.execute(
                text("SELECT previous_state, new_state FROM audit_logs WHERE uuid = :u"),
                {"u": "01HXAUDIT0000000000000000A4"},
            )
            .mappings()
            .fetchone()
        )
        prev_before = row_before["previous_state"]
        new_before = row_before["new_state"]

        redact_audit_logs.run(seeded_audit_db, dry_run=False, secret_key=_TEST_SECRET)

        row_after = (
            seeded_audit_db.execute(
                text("SELECT previous_state, new_state FROM audit_logs WHERE uuid = :u"),
                {"u": "01HXAUDIT0000000000000000A4"},
            )
            .mappings()
            .fetchone()
        )
        # Byte-for-byte unchanged.
        assert row_after["previous_state"] == prev_before
        assert row_after["new_state"] == new_before

    def test_run_hashes_to_email_in_email_send_payload(self, seeded_audit_db):
        from rentivo.scripts import redact_audit_logs

        redact_audit_logs.run(seeded_audit_db, dry_run=False, secret_key=_TEST_SECRET)

        row = (
            seeded_audit_db.execute(
                text("SELECT new_state FROM audit_logs WHERE uuid = :u"),
                {"u": "01HXAUDIT0000000000000000A5"},
            )
            .mappings()
            .fetchone()
        )

        state = json.loads(row["new_state"])
        assert "to_email" not in state
        assert "to_email_hash" in state
        assert isinstance(state["to_email_hash"], str)
        assert len(state["to_email_hash"]) == 16
        # Same hash should be deterministic for the same secret + plaintext.
        from rentivo.scripts.redact_audit_logs import _hash_email

        assert state["to_email_hash"] == _hash_email("alice@example.com", _TEST_SECRET)

        # event and ctx_keys_count are preserved unchanged.
        assert state["event"] == "welcome"
        assert state["ctx_keys_count"] == 2

    def test_main_invokes_run_with_factories(self, seeded_audit_db):
        """Smoke test for the CLI entrypoint."""
        from rentivo.scripts import redact_audit_logs

        fake_settings = MagicMock()
        fake_settings.get_secret_key.return_value = _TEST_SECRET

        with (
            patch.object(redact_audit_logs, "initialize_db"),
            patch.object(redact_audit_logs, "get_connection", return_value=seeded_audit_db),
            patch.object(redact_audit_logs, "settings", fake_settings),
            patch("sys.argv", ["prog"]),
        ):
            redact_audit_logs.main()

        row = (
            seeded_audit_db.execute(
                text("SELECT new_state FROM audit_logs WHERE uuid = :u"),
                {"u": "01HXAUDIT0000000000000000A2"},
            )
            .mappings()
            .fetchone()
        )
        state = json.loads(row["new_state"])
        assert "pix_key" not in state
        assert state["pix_key_set"] is True
