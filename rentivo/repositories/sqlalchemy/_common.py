"""Shared helpers for SQLAlchemy repositories."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from datetime import datetime

from sqlalchemy.engine import RowMapping

from rentivo.constants import SP_TZ
from rentivo.encryption.base import EncryptionBackend


def _now() -> datetime:
    return datetime.now(SP_TZ)


def decrypt_columns(encryption: EncryptionBackend, rows: Sequence[RowMapping], fields: Sequence[str]) -> Iterator[str]:
    """Decrypt the named columns across all rows in a single batched call.

    Collects ``fields`` from each row in row-major order, runs one
    ``decrypt_many``, and returns an iterator the caller drains with
    ``next()`` while reassembling models — so an N-row × M-column page costs
    one decrypt round-trip instead of N×M. Missing/NULL cells decrypt as ``""``.
    """
    return iter(encryption.decrypt_many([row[f] or "" for row in rows for f in fields]))


def _group_rows_by(rows: Iterable[RowMapping], key: str) -> dict[int, list[RowMapping]]:
    """Bucket child rows by a foreign-key column, preserving fetch order within each bucket."""
    grouped: dict[int, list[RowMapping]] = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(row)
    return grouped
