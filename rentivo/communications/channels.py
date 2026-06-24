"""Pluggable send-step for payment reminders (REN-6).

The reminder *decision* (which bill, which offset, dedup) lives in
``PaymentReminderService``; the *delivery* lives behind ``ReminderChannel`` so
a new channel (WhatsApp — idea #1) can plug in later without the service or the
sweep changing. Email is the only channel today and it reuses the existing
``communication.send`` job + email backend by delegating to
``CommunicationService.send``.
"""

from __future__ import annotations

from typing import Protocol

from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.models.communication import Communication
from rentivo.models.recipient import Recipient
from rentivo.services.communication_service import CommunicationService


class ReminderChannel(Protocol):
    """A delivery channel for a single bill's reminder to its recipients."""

    name: str

    def send(
        self,
        *,
        bill: Bill,
        billing: Billing,
        recipients: list[Recipient],
        comm_type: str,
        subject_template: str,
        body_template: str,
        actor=None,
    ) -> list[Communication]:
        """Deliver the reminder; return the per-recipient records created."""
        ...


class EmailReminderChannel:
    """Email channel: reuses the existing communication pipeline end-to-end."""

    name = "email"

    def __init__(self, communication_service: CommunicationService) -> None:
        self._communication_service = communication_service

    def send(
        self,
        *,
        bill: Bill,
        billing: Billing,
        recipients: list[Recipient],
        comm_type: str,
        subject_template: str,
        body_template: str,
        actor=None,
    ) -> list[Communication]:
        return self._communication_service.send(
            bill,
            billing,
            recipients,
            subject_template,
            body_template,
            actor=actor,
            comm_type=comm_type,
        )


def get_reminder_channel(name: str, *, communication_service: CommunicationService) -> ReminderChannel:
    """Resolve a reminder channel by name.

    Only ``email`` is wired today. A future ``whatsapp`` channel registers here
    and the sweep picks it via ``settings.payment_reminder_channel`` — no other
    code changes.
    """
    if name == "email":
        return EmailReminderChannel(communication_service)
    raise ValueError(f"unknown reminder channel: {name!r}")
