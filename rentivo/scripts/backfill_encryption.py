"""Re-encrypt every PII column through the active encryption backend.

Usage:
    python -m rentivo.scripts.backfill_encryption
    python -m rentivo.scripts.backfill_encryption --dry-run

Behavior:
- Walks every PII-bearing row across users, organizations, billings,
  billing_items, bills, bill_line_items, receipts, and user_totp.
- For each PII column: if the value is non-empty AND not already encrypted by
  the active backend, re-writes it as ciphertext.
- ``users.email`` is handled specially: alongside re-encryption, the
  normalized HMAC-SHA256 blind index is written to ``users.email_hash``.
- Idempotent. Re-running is safe.
- ``--dry-run`` prints a count per (table, column) without writing.

Operator note: run this immediately after switching
``RENTIVO_ENCRYPTION_BACKEND`` from ``base64`` to ``kms``. New rows written
between the cutover and the backfill are already encrypted; the backfill
picks up the legacy plaintext rows.
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


def _backfill_users_email(
    conn: Connection,
    encryption: EncryptionBackend,
    *,
    dry_run: bool,
) -> tuple[int, int]:
    """Re-encrypt ``users.email`` and populate ``users.email_hash``.

    The dual-column write is what makes this a separate helper from the
    generic ``_encrypt_column``. Source of truth for the hash is the
    decrypted (or already-plaintext) email value, normalised via
    :func:`rentivo.blind_index.compute_email_hash`.

    Skip path: a row is fully migrated when its email column is encrypted by
    the active backend AND its email_hash is non-NULL. Anything short of that
    gets rewritten.
    """
    from rentivo.blind_index import compute_email_hash

    rows = conn.execute(text("SELECT id, email, email_hash FROM users")).mappings().fetchall()
    rewritten = 0
    skipped = 0
    for row in rows:
        value = row["email"] or ""
        if not value:
            skipped += 1
            continue

        already_encrypted = encryption.is_encrypted(value)
        hash_populated = bool(row["email_hash"])

        if already_encrypted and hash_populated:
            skipped += 1
            continue

        if already_encrypted and not hash_populated:
            # Half-migrated row: email is already ciphertext, just need to
            # populate the hash. Decrypt once for the plaintext source; do NOT
            # re-encrypt — under KMS that would write a new blob for no gain.
            plaintext = encryption.decrypt(value)
            email_hash = compute_email_hash(plaintext)
            if not dry_run:
                conn.execute(
                    text("UPDATE users SET email_hash = :email_hash WHERE id = :id"),
                    {"email_hash": email_hash, "id": row["id"]},
                )
            rewritten += 1
            continue

        # Plaintext row: encrypt + populate hash in one UPDATE.
        plaintext = encryption.decrypt(value)  # no-op on raw plaintext
        ciphertext = encryption.encrypt(plaintext)
        email_hash = compute_email_hash(plaintext)
        if not dry_run:
            conn.execute(
                text("UPDATE users SET email = :email, email_hash = :email_hash WHERE id = :id"),
                {"email": ciphertext, "email_hash": email_hash, "id": row["id"]},
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

    # users.email requires a dual-column write (ciphertext + blind-index hash)
    # and lives outside the generic _TARGETS loop.
    rewritten, skipped = _backfill_users_email(conn, encryption, dry_run=dry_run)
    table.add_row("users", "email + email_hash", str(rewritten), str(skipped))
    grand_rewritten += rewritten
    grand_skipped += skipped
    logger.info(
        "backfill_users_email_done",
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
