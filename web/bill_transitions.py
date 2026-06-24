"""Bill status transition policy for the detail action bar.

The bill status change is the most consequential action in Rentivo (marking a
bill *Pago* drives the revenue/retention loop; *Cancelado* feels irreversible).
The legacy UI exposed every status as a flat ``<select onchange=submit>`` — any
status reachable from any other, no confirmation, silent JS submit.

This module is the single source of truth for *which* transitions are offered
from a given status and *how* each is presented: the dominant next-step action,
the rarer "Alterar status" options, and which transitions are consequential
enough to require an explicit, side-effect-describing confirmation.

It only shapes the UI affordances. The route still validates the submitted
status; defense-in-depth server enforcement of the lifecycle is tracked
separately with the backend.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StatusTransition:
    """One offered transition from the bill's current status.

    ``confirm`` gates a styled confirmation dialog (see ``data-confirm`` in
    ``app.js``) describing the side effect before the form submits. ``variant``
    selects the dialog's accent: ``"primary"`` for positive/expected moves
    (mark paid, reopen), ``"danger"`` for cancel/backward moves.
    """

    to: str
    label: str
    confirm: bool = False
    variant: str = "primary"  # "primary" | "danger"
    confirm_title: str = ""
    confirm_body: str = ""
    confirm_accept: str = ""


# Portuguese (pt-BR) status labels, mirrored from the tags in detail.html.
STATUS_LABELS: dict[str, str] = {
    "draft": "Rascunho",
    "published": "Publicado",
    "sent": "Enviado",
    "paid": "Pago",
    "cancelled": "Cancelado",
    "delayed_payment": "Pag. Atrasado",
}


def _cancel() -> StatusTransition:
    return StatusTransition(
        to="cancelled",
        label="Cancelar fatura",
        confirm=True,
        variant="danger",
        confirm_title="Cancelar esta fatura?",
        confirm_body=(
            "A cobrança é cancelada e deixa de ser tratada como ativa. "
            "Você pode reabri-la depois como rascunho, se precisar."
        ),
        confirm_accept="Cancelar fatura",
    )


_MARK_PAID = StatusTransition(
    to="paid",
    label="Marcar como pago",
    confirm=True,
    variant="primary",
    confirm_title="Marcar fatura como paga?",
    confirm_body=(
        "Isto marca a fatura como paga, libera o recibo e registra a data de "
        "pagamento. Você poderá reverter depois, se necessário."
    ),
    confirm_accept="Marcar como pago",
)


# Per-status policy: an optional dominant "next step" plus the rarer options.
# Keyed by current status; values are (primary | None, [others...]).
_POLICY: dict[str, tuple[StatusTransition | None, list[StatusTransition]]] = {
    "draft": (
        StatusTransition(to="published", label="Publicar fatura"),
        [
            StatusTransition(to="sent", label="Marcar como enviada"),
            _cancel(),
        ],
    ),
    "published": (
        StatusTransition(to="sent", label="Marcar como enviada"),
        [
            _MARK_PAID,
            StatusTransition(
                to="draft",
                label="Voltar para rascunho",
                confirm=True,
                variant="danger",
                confirm_title="Voltar para rascunho?",
                confirm_body=("A fatura volta para rascunho e sai do fluxo de cobrança até ser publicada novamente."),
                confirm_accept="Voltar para rascunho",
            ),
            _cancel(),
        ],
    ),
    "sent": (
        _MARK_PAID,
        [
            StatusTransition(to="delayed_payment", label="Marcar pagamento atrasado"),
            StatusTransition(
                to="published",
                label="Voltar para publicado",
                confirm=True,
                variant="danger",
                confirm_title="Voltar para publicado?",
                confirm_body=(
                    "A fatura volta para publicado. O registro de envio é mantido, "
                    "mas ela deixa de constar como enviada."
                ),
                confirm_accept="Voltar para publicado",
            ),
            _cancel(),
        ],
    ),
    "delayed_payment": (
        _MARK_PAID,
        [
            StatusTransition(to="sent", label="Voltar para enviado"),
            _cancel(),
        ],
    ),
    "paid": (
        None,
        [
            StatusTransition(
                to="sent",
                label="Reverter pagamento",
                confirm=True,
                variant="danger",
                confirm_title="Reverter o pagamento?",
                confirm_body=("Isto reverte o pagamento: a fatura deixa de constar como paga e volta para enviada."),
                confirm_accept="Reverter pagamento",
            ),
            _cancel(),
        ],
    ),
    "cancelled": (
        None,
        [
            StatusTransition(
                to="draft",
                label="Reabrir como rascunho",
                confirm=True,
                variant="primary",
                confirm_title="Reabrir esta fatura?",
                confirm_body=("A fatura é reaberta como rascunho e volta a poder ser editada e publicada."),
                confirm_accept="Reabrir fatura",
            ),
        ],
    ),
}


def transitions_for(status: str) -> tuple[StatusTransition | None, list[StatusTransition]]:
    """Return ``(primary_next_action, other_transitions)`` for ``status``.

    ``primary_next_action`` is the dominant expected move (rendered as
    ``btn--primary``) or ``None`` for terminal states. ``other_transitions`` are
    the rarer moves shown under the "Alterar status" menu. Unknown statuses fall
    back to no offered transitions.
    """

    return _POLICY.get(status, (None, []))
