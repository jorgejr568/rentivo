"""Value object for the billing KPI rollup.

Kept separate from ``billing_stats_service`` so the stats cache layer can import
and (de)serialize it without a circular dependency on the service (which in turn
imports the cache factory).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rentivo.models.bill import BillSummary


@dataclass(frozen=True)
class BillingStats:
    """Year-to-date rollup across a set of billings, plus each billing's current bill.

    All money values are in centavos. ``year`` is the calendar year the rollup
    covers. ``current`` maps ``billing_id`` to its latest :class:`BillSummary`
    (any year, including cancelled bills so the table can still render their
    status); billings without any bill are absent.
    """

    year: int = 0
    expected: int = 0
    received: int = 0
    pending: int = 0
    overdue: int = 0
    paid_count: int = 0
    pending_count: int = 0
    overdue_count: int = 0
    current: dict[int, BillSummary] = field(default_factory=dict)

    @property
    def active_count(self) -> int:
        return self.pending_count + self.overdue_count

    @property
    def billed_count(self) -> int:
        return self.paid_count + self.pending_count + self.overdue_count

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (used by the Redis stats cache)."""
        return {
            "year": self.year,
            "expected": self.expected,
            "received": self.received,
            "pending": self.pending,
            "overdue": self.overdue,
            "paid_count": self.paid_count,
            "pending_count": self.pending_count,
            "overdue_count": self.overdue_count,
            "current": {str(bid): s.model_dump() for bid, s in self.current.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BillingStats":
        return cls(
            year=data["year"],
            expected=data["expected"],
            received=data["received"],
            pending=data["pending"],
            overdue=data["overdue"],
            paid_count=data["paid_count"],
            pending_count=data["pending_count"],
            overdue_count=data["overdue_count"],
            current={int(bid): BillSummary(**s) for bid, s in data["current"].items()},
        )
