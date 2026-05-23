"""Shared helpers for SQLAlchemy repositories."""

from __future__ import annotations

from datetime import datetime

from rentivo.constants import SP_TZ


def _now() -> datetime:
    return datetime.now(SP_TZ)
