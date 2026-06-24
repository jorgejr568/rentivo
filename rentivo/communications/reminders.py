"""Pure logic for automated payment reminders / dunning (REN-6).

No I/O lives here — just the rules for *when* a bill earns a reminder and how
each reminder is labelled. Keeping it side-effect free makes the offset / dedup
behaviour cheap to unit-test and keeps the channel/sweep wiring thin.

Offset convention (``payment_reminder_offset_days``): the number of days from
*today* to the bill's due date. Positive means today is *before* the due date
(``3`` → D-3, a heads-up), ``0`` is the due date itself, negative means *after*
the due date (``-3`` → D+3, a dunning nudge).
"""

from __future__ import annotations

from datetime import date, datetime

from rentivo.models.bill import BillStatus

# Template key used to resolve the reminder copy (billing -> owner -> system
# default). Every offset shares one editable template; the per-offset suffix
# only exists on the stored Communication row for dedup.
REMINDER_TEMPLATE_COMM_TYPE = "payment_reminder"

# Statuses that are eligible for a reminder: the bill has been issued to the
# tenant but isn't settled. DRAFT (not sent yet), PAID (done) and CANCELLED
# (void) are all skipped. DELAYED_PAYMENT is an unpaid, overdue bill — exactly
# what dunning targets — so it stays in.
REMINDABLE_BILL_STATUSES: frozenset[str] = frozenset(
    {
        BillStatus.PUBLISHED.value,
        BillStatus.SENT.value,
        BillStatus.DELAYED_PAYMENT.value,
    }
)

# Accepted human-entered due-date formats. due_date is free text in the UI;
# the canonical form is Brazilian DD/MM/YYYY, but we also accept ISO so an
# imported/automated bill still gets reminders.
_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d")


def parse_offset_days(raw: str) -> list[int]:
    """Parse the comma-separated ``payment_reminder_offset_days`` setting.

    Blank entries are ignored; non-integers raise ``ValueError`` so a typo'd
    config fails loudly at startup rather than silently sending nothing.
    Duplicates are collapsed, order preserved (first occurrence wins).
    """
    out: list[int] = []
    seen: set[int] = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        value = int(part)
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def parse_due_date(due_date: str | None) -> date | None:
    """Parse a free-text due date to a ``date``; ``None`` if blank/unparseable."""
    if not due_date:
        return None
    text = due_date.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def days_until_due(due_date: str | None, today: date) -> int | None:
    """Days from ``today`` to the bill's due date, or ``None`` if unparseable.

    Positive = due in the future, 0 = due today, negative = overdue.
    """
    parsed = parse_due_date(due_date)
    if parsed is None:
        return None
    return (parsed - today).days


def offset_comm_type(offset_days: int) -> str:
    """Stable per-offset comm_type for the stored Communication row.

    e.g. ``3 -> payment_reminder:d-3`` (3 days before due),
    ``0 -> payment_reminder:due``, ``-3 -> payment_reminder:d+3``.
    The suffix makes each offset a distinct row so the sweep can dedup a
    reminder it already sent for that bill+offset.
    """
    if offset_days > 0:
        suffix = f"d-{offset_days}"
    elif offset_days == 0:
        suffix = "due"
    else:
        suffix = f"d+{abs(offset_days)}"
    return f"{REMINDER_TEMPLATE_COMM_TYPE}:{suffix}"
