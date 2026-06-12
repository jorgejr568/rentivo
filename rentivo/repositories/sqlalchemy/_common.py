"""Shared helpers for SQLAlchemy repositories."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy.engine import RowMapping

from rentivo.constants import SP_TZ


def _now() -> datetime:
    return datetime.now(SP_TZ)


def _group_rows_by(rows: Iterable[RowMapping], key: str) -> dict[int, list[RowMapping]]:
    """Bucket child rows by a foreign-key column, preserving fetch order within each bucket."""
    grouped: dict[int, list[RowMapping]] = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(row)
    return grouped
