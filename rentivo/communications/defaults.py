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
