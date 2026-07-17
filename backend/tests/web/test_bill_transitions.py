"""Tests for the bill status transition policy (web/bill_transitions.py).

Covers the lifecycle guardrails behind REN-11: the dominant next-step action,
the constrained set of "other" transitions, and which transitions are flagged
as consequential (require a confirmation dialog).
"""

from __future__ import annotations

from legacy_web.bill_transitions import STATUS_LABELS, transitions_for
from rentivo.models.bill import ALLOWED_STATUS_TRANSITIONS, BillStatus


def _offered_targets(status: str) -> set[str]:
    """The set of target statuses the UI policy offers from ``status``."""
    primary, others = transitions_for(status)
    offered = ([primary] if primary else []) + list(others)
    return {t.to for t in offered}


def test_expected_primary_next_action_per_status():
    # The dominant button matches the intended lifecycle.
    assert transitions_for("draft")[0].to == "published"
    assert transitions_for("published")[0].to == "sent"
    assert transitions_for("sent")[0].to == "paid"
    assert transitions_for("delayed_payment")[0].to == "paid"
    # Terminal-ish states offer no dominant forward action.
    assert transitions_for("paid")[0] is None
    assert transitions_for("cancelled")[0] is None


def test_mark_paid_is_a_confirmed_primary_transition():
    primary, _ = transitions_for("sent")
    assert primary.to == "paid"
    assert primary.confirm is True
    assert primary.variant == "primary"
    assert primary.label == "Marcar como pago"
    assert primary.confirm_body  # describes the side effect


def test_cancel_requires_danger_confirmation_from_every_non_terminal_state():
    for status in ("draft", "published", "sent", "delayed_payment", "paid"):
        _, others = transitions_for(status)
        cancel = next(t for t in others if t.to == "cancelled")
        assert cancel.confirm is True
        assert cancel.variant == "danger"
        assert cancel.confirm_body


def test_backward_transitions_require_confirmation():
    # published -> draft, sent -> published, paid -> sent are all backward moves.
    backward = {
        "published": "draft",
        "sent": "published",
        "paid": "sent",
    }
    for frm, to in backward.items():
        _, others = transitions_for(frm)
        move = next(t for t in others if t.to == to)
        assert move.confirm is True, f"{frm}->{to} should confirm"


def test_forward_lateral_moves_do_not_force_confirmation():
    # Publishing / marking sent / flagging delayed are not destructive.
    assert transitions_for("draft")[0].confirm is False  # -> published
    assert transitions_for("published")[0].confirm is False  # -> sent
    _, sent_others = transitions_for("sent")
    delayed = next(t for t in sent_others if t.to == "delayed_payment")
    assert delayed.confirm is False


def test_all_offered_transitions_are_valid_bill_statuses():
    for status in STATUS_LABELS:
        primary, others = transitions_for(status)
        offered = ([primary] if primary else []) + list(others)
        for t in offered:
            # Must not raise — every target is a real BillStatus.
            BillStatus(t.to)
            # And never a no-op self-transition.
            assert t.to != status


def test_unknown_status_offers_nothing():
    assert transitions_for("not_a_status") == (None, [])


def test_ui_policy_matches_server_lifecycle():
    """Defense-in-depth (REN-21): the UI affordance policy and the server-enforced
    ALLOWED_STATUS_TRANSITIONS must not drift. Every status offered in the UI must
    match exactly the set of transitions the backend will accept."""
    for status in ALLOWED_STATUS_TRANSITIONS:
        assert _offered_targets(status) == set(ALLOWED_STATUS_TRANSITIONS[status]), (
            f"UI policy and server lifecycle disagree for status {status!r}"
        )
    # Every status that offers UI transitions is also a key in the server map.
    for status in STATUS_LABELS:
        if _offered_targets(status):
            assert status in ALLOWED_STATUS_TRANSITIONS, f"{status!r} offers transitions but has no server policy"
