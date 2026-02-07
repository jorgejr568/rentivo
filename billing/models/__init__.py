def format_brl(centavos: int) -> str:
    """Format centavos as BRL string: 285000 -> 'R$ 2.850,00'"""
    reais = centavos / 100
    formatted = f"{reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"
