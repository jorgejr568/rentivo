"""Backfill: redact plaintext PIX from existing ``audit_logs`` rows.

Usage:
    python -m rentivo.scripts.redact_audit_logs
    python -m rentivo.scripts.redact_audit_logs --dry-run

Behavior:
- Walks every ``audit_logs`` row.
- For each row, parses ``previous_state`` and ``new_state`` JSON (each may be NULL).
- If the parsed dict contains any of ``pix_key`` / ``pix_merchant_name`` /
  ``pix_merchant_city`` as keys, replaces them with ``<key>_set: bool(value)``
  presence booleans.
- Writes back the rewritten JSON only if the dict actually changed.
- Idempotent. Re-running on already-redacted rows is a no-op.

Operator note: run this once after deploying the redacted serializers
(``rentivo/services/audit_serializers.py``). New audit rows written after that
deploy already have the redacted shape; this script handles the legacy backlog.
"""

from __future__ import annotations

import json
import sys

import structlog
from rich.console import Console
from rich.table import Table
from sqlalchemy import Connection, text

from rentivo.db import get_connection, initialize_db
from rentivo.logging import configure_logging

logger = structlog.get_logger(__name__)
console = Console()


_PII_KEYS = ("pix_key", "pix_merchant_name", "pix_merchant_city")


def _redact_state(state_json: str | None) -> tuple[str | None, bool]:
    """Return (rewritten_json, changed). ``changed`` is True iff any PII key
    was rewritten. ``state_json`` of None / empty is passed through unchanged
    with changed=False."""
    if state_json is None or state_json == "":
        return state_json, False
    try:
        data = json.loads(state_json)
    except TypeError, ValueError:
        # Not a valid JSON object — leave as-is. Audit logs are append-only;
        # corrupting one row by parsing it as something it isn't would be worse
        # than leaving the leak in place.
        return state_json, False
    if not isinstance(data, dict):
        return state_json, False

    changed = False
    for key in _PII_KEYS:
        if key in data:
            value = data.pop(key)
            data[f"{key}_set"] = bool(value)
            changed = True

    if not changed:
        return state_json, False
    return json.dumps(data), True


def run(conn: Connection, *, dry_run: bool) -> None:
    label = "[yellow]DRY-RUN[/yellow]" if dry_run else "[green]LIVE[/green]"
    console.print(f"\n[bold]Redact audit_logs[/bold] {label}\n")

    rows = conn.execute(text("SELECT id, previous_state, new_state FROM audit_logs")).mappings().fetchall()
    rewritten = 0
    skipped = 0
    for row in rows:
        prev_new, prev_changed = _redact_state(row["previous_state"])
        new_new, new_changed = _redact_state(row["new_state"])
        if not (prev_changed or new_changed):
            skipped += 1
            continue
        if not dry_run:
            conn.execute(
                text("UPDATE audit_logs SET previous_state = :prev, new_state = :new WHERE id = :id"),
                {"prev": prev_new, "new": new_new, "id": row["id"]},
            )
        rewritten += 1

    if not dry_run:
        conn.commit()

    table = Table(title="Redaction summary")
    table.add_column("Outcome", style="bold")
    table.add_column("Rows", justify="right")
    table.add_row("Rewritten", str(rewritten))
    table.add_row("Skipped (no PII)", str(skipped))
    console.print(table)
    logger.info(
        "redact_audit_logs_done",
        rewritten=rewritten,
        skipped=skipped,
        dry_run=dry_run,
    )

    if dry_run:
        console.print("[yellow]Re-run without --dry-run to apply.[/yellow]")


def main() -> None:
    configure_logging(cli=True)
    dry_run = "--dry-run" in sys.argv
    initialize_db()
    conn = get_connection()
    run(conn, dry_run=dry_run)


if __name__ == "__main__":  # pragma: no cover
    main()
