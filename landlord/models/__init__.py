def format_brl(centavos: int) -> str:
    """Format centavos as BRL string: 285000 -> 'R$ 2.850,00'"""
    reais = centavos / 100
    formatted = f"{reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def parse_brl(text: str) -> int | None:
    """Parse a BRL amount string into centavos. Returns None on invalid input.

    Accepts formats like '2850', '2850.00', '2.850,00', '2850,50'.
    """
    text = text.strip()
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return int(round(float(text) * 100))
    except ValueError:
        return None
