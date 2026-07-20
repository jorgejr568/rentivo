"""Tests for the shared bill status transition policy."""

from __future__ import annotations

from rentivo.bill_transitions import STATUS_LABELS, transitions_for
from rentivo.models.bill import ALLOWED_STATUS_TRANSITIONS, BillStatus


def _offered_targets(status: str) -> set[str]:
    """The set of target statuses the UI policy offers from ``status``."""
    primary, others = transitions_for(status)
    offered = ([primary] if primary else []) + list(others)
    return {transition.to for transition in offered}


def test_expected_primary_next_action_per_status():
    assert transitions_for("draft")[0].to == "published"
    assert transitions_for("published")[0].to == "sent"
    assert transitions_for("sent")[0].to == "paid"
    assert transitions_for("delayed_payment")[0].to == "paid"
    assert transitions_for("paid")[0] is None
    assert transitions_for("cancelled")[0] is None


def test_mark_paid_is_a_confirmed_primary_transition():
    primary, _ = transitions_for("sent")
    assert primary.to == "paid"
    assert primary.confirm is True
    assert primary.variant == "primary"
    assert primary.label == "Marcar como pago"
    assert primary.confirm_body


def test_cancel_requires_danger_confirmation_from_every_non_terminal_state():
    for status in ("draft", "published", "sent", "delayed_payment", "paid"):
        _, others = transitions_for(status)
        cancel = next(transition for transition in others if transition.to == "cancelled")
        assert cancel.confirm is True
        assert cancel.variant == "danger"
        assert cancel.confirm_body


def test_backward_transitions_require_confirmation():
    backward = {"published": "draft", "sent": "published", "paid": "sent"}
    for current, target in backward.items():
        _, others = transitions_for(current)
        move = next(transition for transition in others if transition.to == target)
        assert move.confirm is True, f"{current}->{target} should confirm"


def test_forward_lateral_moves_do_not_force_confirmation():
    assert transitions_for("draft")[0].confirm is False
    assert transitions_for("published")[0].confirm is False
    _, sent_others = transitions_for("sent")
    delayed = next(transition for transition in sent_others if transition.to == "delayed_payment")
    assert delayed.confirm is False


def test_all_offered_transitions_are_valid_bill_statuses():
    for status in STATUS_LABELS:
        primary, others = transitions_for(status)
        offered = ([primary] if primary else []) + list(others)
        for transition in offered:
            BillStatus(transition.to)
            assert transition.to != status


def test_unknown_status_offers_nothing():
    assert transitions_for("not_a_status") == (None, [])


def test_ui_policy_matches_server_lifecycle():
    for status in ALLOWED_STATUS_TRANSITIONS:
        assert _offered_targets(status) == set(ALLOWED_STATUS_TRANSITIONS[status]), (
            f"UI policy and server lifecycle disagree for status {status!r}"
        )
    for status in STATUS_LABELS:
        if _offered_targets(status):
            assert status in ALLOWED_STATUS_TRANSITIONS, f"{status!r} offers transitions but has no server policy"
