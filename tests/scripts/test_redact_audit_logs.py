"""Tests for the audit-log PII redaction backfill script."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from sqlalchemy import text


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
            # Already redacted (partial-mask format) — must be skipped.
            "uuid": "01HXAUDIT0000000000000000A4",
            "event_type": "billing.update",
            "actor_id": 1,
            "actor_username": "alice@example.com",
            "source": "web",
            "entity_type": "billing",
            "entity_id": 2,
            "entity_uuid": "01HXBILLING0000000000000002",
            "previous_state": json.dumps({"id": 2, "name": "Apt 202", "pix_key": "abc...xy"}),
            "new_state": json.dumps({"id": 2, "name": "Apt 202 v2", "pix_key": "abc...xy"}),
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

        redact_audit_logs.run(seeded_audit_db, dry_run=True)

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

        redact_audit_logs.run(seeded_audit_db, dry_run=False)

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

        # PIX values are partial-mask redacted in-place under their original
        # field names. Hash and presence-boolean forms are gone.
        assert prev["pix_key"] == "ali...om"  # 'alice@pix.com' (13 chars) → 'ali...om'
        assert prev["pix_merchant_name"] == "***"  # 'Alice' (5 chars) collapses
        assert prev["pix_merchant_city"] == "Sao...lo"  # 'Sao Paulo' (9 chars)
        for prefix_key in ("pix_key", "pix_merchant_name", "pix_merchant_city"):
            assert f"{prefix_key}_set" not in prev
            assert f"{prefix_key}_hash" not in prev
        assert new["pix_key"] == prev["pix_key"]  # same PIX, redaction is deterministic

        # Non-PIX fields are preserved untouched.
        assert prev["id"] == 1
        assert prev["name"] == "Apt 101"
        assert new["name"] == "Apt 101 (renamed)"
        assert prev["owner_id"] == 5

    def test_run_redacts_user_new_state(self, seeded_audit_db):
        from rentivo.scripts import redact_audit_logs

        redact_audit_logs.run(seeded_audit_db, dry_run=False)

        row = (
            seeded_audit_db.execute(
                text("SELECT new_state FROM audit_logs WHERE uuid = :u"),
                {"u": "01HXAUDIT0000000000000000A2"},
            )
            .mappings()
            .fetchone()
        )

        state = json.loads(row["new_state"])
        assert state["pix_key"] == "ali...om"
        assert state["pix_merchant_name"] == "***"
        assert state["pix_merchant_city"] == "Sao...lo"
        for prefix_key in ("pix_key", "pix_merchant_name", "pix_merchant_city"):
            assert f"{prefix_key}_set" not in state
            assert f"{prefix_key}_hash" not in state
        # email field on user serialization is untouched here — this is just JSON content
        assert state["email"] == "alice@example.com"

    def test_run_handles_null_states(self, seeded_audit_db):
        """Login events have null previous_state and new_state. Must not crash."""
        from rentivo.scripts import redact_audit_logs

        redact_audit_logs.run(seeded_audit_db, dry_run=False)

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

        redact_audit_logs.run(seeded_audit_db, dry_run=False)
        redact_audit_logs.run(seeded_audit_db, dry_run=False)

        row = (
            seeded_audit_db.execute(
                text("SELECT new_state FROM audit_logs WHERE uuid = :u"),
                {"u": "01HXAUDIT0000000000000000A1"},
            )
            .mappings()
            .fetchone()
        )

        # Idempotency: second run of the backfill against rows that are
        # already partial-mask redacted is a byte-for-byte no-op because
        # redact(redacted_value) == redacted_value for typical inputs.
        state = json.loads(row["new_state"])
        assert state["pix_key"] == "ali...om"
        assert "pix_key_hash" not in state
        assert "pix_key_set" not in state

    def test_skips_already_redacted_row(self, seeded_audit_db):
        """A row whose JSON already uses partial-mask redaction is left untouched."""
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

        redact_audit_logs.run(seeded_audit_db, dry_run=False)

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

    def test_run_redacts_to_email_in_email_send_payload(self, seeded_audit_db):
        from rentivo.scripts import redact_audit_logs

        redact_audit_logs.run(seeded_audit_db, dry_run=False)

        row = (
            seeded_audit_db.execute(
                text("SELECT new_state FROM audit_logs WHERE uuid = :u"),
                {"u": "01HXAUDIT0000000000000000A5"},
            )
            .mappings()
            .fetchone()
        )

        state = json.loads(row["new_state"])
        # to_email is partial-mask redacted in place under its original key.
        assert state["to_email"] == "al...@example.com"
        assert "to_email_hash" not in state

        # event and ctx_keys_count are preserved unchanged.
        assert state["event"] == "welcome"
        assert state["ctx_keys_count"] == 2

    def test_main_invokes_run_with_factories(self, seeded_audit_db):
        from rentivo.scripts import redact_audit_logs

        with (
            patch.object(redact_audit_logs, "initialize_db"),
            patch.object(redact_audit_logs, "get_connection", return_value=seeded_audit_db),
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
        assert state["pix_key"] == "ali...om"
        assert "pix_key_hash" not in state
        assert "pix_key_set" not in state
