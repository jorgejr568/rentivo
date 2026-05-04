"""Re-encrypt every PII column through the active encryption backend.

Usage:
    python -m rentivo.scripts.backfill_encryption
    python -m rentivo.scripts.backfill_encryption --dry-run

Behavior:
- Walks every ``users``, ``organizations``, ``billings``, ``billing_items``,
  ``bills``, ``bill_line_items``, ``receipts``, and ``user_totp`` row.
- For each PII column: if the value is non-empty AND not already encrypted by
  the active backend, re-writes it as ciphertext.
- Idempotent. Re-running is safe.
- ``--dry-run`` prints a count per (table, column) without writing.

Operator note: run this immediately after switching
``RENTIVO_ENCRYPTION_BACKEND`` from ``base64`` to ``kms``. New rows written
between the cutover and the backfill are already encrypted; the backfill picks
up the legacy plaintext rows.
"""

from __future__ import annotations

import sys

import structlog
from rich.console import Console
from rich.table import Table
from sqlalchemy import Connection, text

from rentivo.db import get_connection, initialize_db
from rentivo.encryption.base import EncryptionBackend
from rentivo.encryption.factory import get_encryption
from rentivo.logging import configure_logging

logger = structlog.get_logger(__name__)
console = Console()


# (table, primary_key_column, [pii_column, ...])
_TARGETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("users", "id", ("pix_key", "pix_merchant_name", "pix_merchant_city")),
    ("organizations", "id", ("pix_key", "pix_merchant_name", "pix_merchant_city")),
    ("billings", "id", ("pix_key", "pix_merchant_name", "pix_merchant_city", "description", "name")),
    ("billing_items", "id", ("description",)),
    ("bills", "id", ("notes",)),
    ("bill_line_items", "id", ("description",)),
    ("receipts", "id", ("filename",)),
    ("user_totp", "id", ("secret",)),
)


def _encrypt_column(
    conn: Connection,
    encryption: EncryptionBackend,
    table: str,
    pk_column: str,
    column: str,
    *,
    dry_run: bool,
) -> tuple[int, int]:
    """Encrypt ``column`` in ``table``. Returns (rewritten_count, skipped_count).

    Skip path: ``is_encrypted(value)`` matches **only** the active backend's
    format. We can't compare ``encrypt(decrypt(value)) == value`` for skipping
    because KMS encryption is non-deterministic (re-encrypting plaintext yields
    a different blob each time).

    Rewrite path: ``encrypt(decrypt(value))`` round-trips through plaintext.
    This is what makes a base64->kms backfill safe: KMSBackend.decrypt knows how
    to unwrap a ``b64:v1:`` row, so we re-encrypt the original plaintext under
    KMS rather than wrapping the literal ``b64:v1:...`` string.
    """
    rows = (
        conn.execute(text(f"SELECT {pk_column} AS pk, {column} AS val FROM {table}"))  # noqa: S608
        .mappings()
        .fetchall()
    )
    rewritten = 0
    skipped = 0
    for row in rows:
        value = row["val"] or ""
        if value == "" or encryption.is_encrypted(value):
            skipped += 1
            continue
        ciphertext = encryption.encrypt(encryption.decrypt(value))
        if not dry_run:
            conn.execute(
                text(f"UPDATE {table} SET {column} = :val WHERE {pk_column} = :pk"),  # noqa: S608
                {"val": ciphertext, "pk": row["pk"]},
            )
        rewritten += 1
    if not dry_run:
        conn.commit()
    return rewritten, skipped


def run(conn: Connection, encryption: EncryptionBackend, *, dry_run: bool) -> None:
    label = "[yellow]DRY-RUN[/yellow]" if dry_run else "[green]LIVE[/green]"
    console.print(f"\n[bold]Backfill encryption[/bold] {label}\n")

    table = Table(title="Backfill summary")
    table.add_column("Table", style="bold")
    table.add_column("Column")
    table.add_column("Rewritten", justify="right", style="green")
    table.add_column("Skipped", justify="right", style="dim")

    grand_rewritten = 0
    grand_skipped = 0
    for table_name, pk_column, columns in _TARGETS:
        for column in columns:
            rewritten, skipped = _encrypt_column(
                conn,
                encryption,
                table_name,
                pk_column,
                column,
                dry_run=dry_run,
            )
            table.add_row(table_name, column, str(rewritten), str(skipped))
            grand_rewritten += rewritten
            grand_skipped += skipped
            logger.info(
                "backfill_column_done",
                table=table_name,
                column=column,
                rewritten=rewritten,
                skipped=skipped,
                dry_run=dry_run,
            )

    console.print(table)
    console.print(f"\n[bold]Total:[/bold] {grand_rewritten} rewritten, {grand_skipped} skipped.")
    if dry_run:
        console.print("[yellow]Re-run without --dry-run to apply.[/yellow]")


def main() -> None:
    configure_logging(cli=True)
    dry_run = "--dry-run" in sys.argv
    initialize_db()
    conn = get_connection()
    encryption = get_encryption()
    run(conn, encryption, dry_run=dry_run)


if __name__ == "__main__":  # pragma: no cover
    main()
