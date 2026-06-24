"""System-default communication templates (PT-BR), seeded from the landlord's
real copy. Used as the lowest-priority fallback when no billing/org/user
template exists for a communication type.
"""

from __future__ import annotations

from rentivo.models.communication import CommType, CommunicationTemplate

DEFAULT_BILL_READY_SUBJECT = "Cobrança {{unidade}} — {{mes}}"

DEFAULT_BILL_READY_BODY = (
    "Prezado {{nome_inquilino}},\n"
    "\n"
    "Espero que este e-mail o encontre bem.\n"
    "\n"
    "Estou enviando este e-mail referente à unidade **{{unidade}}**. Segue em anexo "
    "a cobrança referente aos valores do mês de **{{mes}}**.\n"
    "\n"
    "Por favor, sinta-se à vontade para entrar em contato caso tenha alguma dúvida.\n"
    "\n"
    "Atenciosamente."
)

DEFAULT_PAYMENT_REMINDER_SUBJECT = "Lembrete de pagamento — {{unidade}} ({{mes}})"

DEFAULT_PAYMENT_REMINDER_BODY = (
    "Prezado {{nome_inquilino}},\n"
    "\n"
    "Este é um lembrete amigável sobre a cobrança da unidade **{{unidade}}** "
    "referente ao mês de **{{mes}}**, no valor de **{{total}}**, com vencimento "
    "em **{{vencimento}}**.\n"
    "\n"
    "Se o pagamento já foi efetuado, por favor desconsidere este e-mail. Caso "
    "contrário, agradecemos a regularização e ficamos à disposição para qualquer "
    "dúvida.\n"
    "\n"
    "Atenciosamente."
)

DEFAULT_PAYMENT_RECEIPT_SUBJECT = "Recibo de pagamento {{unidade}} — {{mes}}"

DEFAULT_PAYMENT_RECEIPT_BODY = (
    "Prezado {{nome_inquilino}},\n"
    "\n"
    "Confirmamos o recebimento do pagamento referente à unidade **{{unidade}}**, "
    "no valor de **{{total}}**, relativo ao mês de **{{mes}}**.\n"
    "\n"
    "Segue em anexo o **recibo de pagamento** correspondente.\n"
    "\n"
    "Agradecemos e permanecemos à disposição para qualquer dúvida.\n"
    "\n"
    "Atenciosamente."
)

_DEFAULTS: dict[str, tuple[str, str]] = {
    CommType.BILL_READY.value: (DEFAULT_BILL_READY_SUBJECT, DEFAULT_BILL_READY_BODY),
    CommType.PAYMENT_RECEIPT.value: (DEFAULT_PAYMENT_RECEIPT_SUBJECT, DEFAULT_PAYMENT_RECEIPT_BODY),
    # Reminders use a free-form template type (not a CommType enum member): the
    # base key plus offset-specific suffixes (e.g. "payment_reminder:d-3").
    # See rentivo.communications.reminders.REMINDER_TEMPLATE_COMM_TYPE.
    "payment_reminder": (DEFAULT_PAYMENT_REMINDER_SUBJECT, DEFAULT_PAYMENT_REMINDER_BODY),
}


def system_default_template(comm_type: str) -> CommunicationTemplate:
    """Return the built-in default template for ``comm_type``.

    ``owner_type='system'`` / ``owner_id=0`` mark it as the synthetic fallback;
    it is never persisted.
    """
    subject, body = _DEFAULTS[comm_type]
    return CommunicationTemplate(
        owner_type="system",
        owner_id=0,
        comm_type=comm_type,
        subject=subject,
        body_markdown=body,
    )
