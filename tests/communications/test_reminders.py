from __future__ import annotations

from datetime import date

import pytest

from rentivo.communications.reminders import (
    REMINDABLE_BILL_STATUSES,
    days_until_due,
    offset_comm_type,
    parse_due_date,
    parse_offset_days,
)
from rentivo.models.bill import BillStatus


class TestParseOffsetDays:
    def test_parses_comma_separated(self):
        assert parse_offset_days("3,0,-3") == [3, 0, -3]

    def test_ignores_blanks_and_whitespace(self):
        assert parse_offset_days(" 3 , , 0 ,-3,") == [3, 0, -3]

    def test_collapses_duplicates_preserving_order(self):
        assert parse_offset_days("3,3,0,3") == [3, 0]

    def test_empty_is_empty_list(self):
        assert parse_offset_days("") == []
        assert parse_offset_days("   ") == []

    def test_non_integer_raises(self):
        with pytest.raises(ValueError):
            parse_offset_days("3,abc")


class TestParseDueDate:
    def test_brazilian_format(self):
        assert parse_due_date("10/04/2025") == date(2025, 4, 10)

    def test_iso_format(self):
        assert parse_due_date("2025-04-10") == date(2025, 4, 10)

    def test_blank_or_none_is_none(self):
        assert parse_due_date("") is None
        assert parse_due_date(None) is None

    def test_unparseable_is_none(self):
        assert parse_due_date("vence amanhã") is None


class TestDaysUntilDue:
    def test_future_is_positive(self):
        assert days_until_due("13/06/2026", date(2026, 6, 10)) == 3

    def test_due_today_is_zero(self):
        assert days_until_due("10/06/2026", date(2026, 6, 10)) == 0

    def test_overdue_is_negative(self):
        assert days_until_due("07/06/2026", date(2026, 6, 10)) == -3

    def test_unparseable_is_none(self):
        assert days_until_due("???", date(2026, 6, 10)) is None


class TestOffsetCommType:
    def test_before_due(self):
        assert offset_comm_type(3) == "payment_reminder:d-3"

    def test_on_due(self):
        assert offset_comm_type(0) == "payment_reminder:due"

    def test_after_due(self):
        assert offset_comm_type(-3) == "payment_reminder:d+3"

    def test_each_offset_is_distinct(self):
        kinds = {offset_comm_type(o) for o in (3, 0, -3)}
        assert len(kinds) == 3


def test_remindable_statuses_exclude_paid_draft_cancelled():
    assert BillStatus.PAID.value not in REMINDABLE_BILL_STATUSES
    assert BillStatus.DRAFT.value not in REMINDABLE_BILL_STATUSES
    assert BillStatus.CANCELLED.value not in REMINDABLE_BILL_STATUSES
    assert BillStatus.SENT.value in REMINDABLE_BILL_STATUSES
    assert BillStatus.PUBLISHED.value in REMINDABLE_BILL_STATUSES
    assert BillStatus.DELAYED_PAYMENT.value in REMINDABLE_BILL_STATUSES
