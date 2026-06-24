"""WhatsApp deep-link ("click to chat") helpers.

Builds ``https://wa.me/<phone>?text=<prefilled>`` links so a landlord can send
an invoice over WhatsApp in one tap — no BSP / Cloud API, zero per-message cost.
The prefilled message carries the invoice essentials plus the PIX copia-e-cola
string so the tenant can pay straight from the chat.

Phone numbers are normalized to the bare international digits wa.me expects
(no ``+``, spaces, or punctuation). Bare Brazilian numbers (10–11 digits) are
assumed to be national and get the ``55`` country code prepended.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from rentivo.constants import format_month
from rentivo.models import format_brl

WA_ME_BASE = "https://wa.me"

# E.164 allows up to 15 digits; a country code is at least 1. wa.me wants the
# full international number as bare digits.
_MIN_INTL_DIGITS = 11
_MAX_INTL_DIGITS = 15


def normalize_wa_phone(phone: str | None) -> str | None:
    """Normalize a phone number to the bare international digits wa.me expects.

    Returns ``None`` when ``phone`` is empty or cannot be coerced into a
    plausible international number.

    - Strips every non-digit character (``+``, spaces, ``()``, ``-``).
    - A 10- or 11-digit national Brazilian number (DDD + line) is prefixed
      with the ``55`` country code.
    - A number already carrying a country code (12–15 digits) is kept as-is.
    """
    if not phone:
        return None
    # A leading "+" means the caller already gave a full international number,
    # so we must not second-guess the country code.
    has_country_code = phone.lstrip().startswith("+")
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    # Bare national BR number (DDD + 8 or 9 digit line) -> add country code.
    if not has_country_code and len(digits) in (10, 11):
        digits = f"55{digits}"
    if _MIN_INTL_DIGITS <= len(digits) <= _MAX_INTL_DIGITS:
        return digits
    return None


def build_invoice_message(
    *,
    billing_name: str,
    reference_month: str,
    amount_centavos: int,
    due_date: str | None,
    pix_payload: str,
) -> str:
    """Build the PT-BR prefilled WhatsApp message for an invoice.

    Includes the unit/billing name, the reference month, the amount in BRL, the
    due date when present, and the PIX copia-e-cola string for one-tap payment.
    """
    lines = [
        f"Olá! Segue a cobrança de *{billing_name}* referente a *{format_month(reference_month)}*.",
        "",
        f"Valor: *{format_brl(amount_centavos)}*",
    ]
    if due_date:
        lines.append(f"Vencimento: *{due_date}*")
    lines += [
        "",
        "PIX copia e cola:",
        pix_payload,
    ]
    return "\n".join(lines)


def build_whatsapp_link(phone: str | None, message: str) -> str | None:
    """Build a ``wa.me`` deep link for ``phone`` prefilled with ``message``.

    Returns ``None`` when the phone number cannot be normalized, so callers can
    cleanly skip recipients without a usable WhatsApp number.
    """
    normalized = normalize_wa_phone(phone)
    if normalized is None:
        return None
    return f"{WA_ME_BASE}/{normalized}?text={quote(message)}"
