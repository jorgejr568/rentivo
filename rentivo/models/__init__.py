from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def format_brl(centavos: int) -> str:
    """Format centavos as BRL string: 285000 -> 'R$ 2.850,00'"""
    return f"R$ {format_brl_input(centavos)}"


def format_brl_input(centavos: int) -> str:
    """Format centavos for form inputs (no R$ prefix): 285000 -> '2.850,00'"""
    sign = "-" if centavos < 0 else ""
    integer, fraction = divmod(abs(centavos), 100)
    integer_str = f"{integer:,}".replace(",", ".")
    return f"{sign}{integer_str},{fraction:02d}"


def parse_brl(text: str) -> int | None:
    """Parse a BRL amount string into non-negative centavos. Returns None on invalid input.

    Accepts formats like '2850', '2850.00', '2.850,00', '2850,50'.
    Uses Decimal with ROUND_HALF_UP to avoid float/banker's-rounding artifacts.
    Rejects negatives — monetary fields in this system are non-negative.
    """
    text = text.strip()
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if value < 0:
        return None
    centavos = (value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(centavos)
