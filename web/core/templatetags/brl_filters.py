from django import template

from landlord.models import format_brl as _format_brl

register = template.Library()


@register.filter
def format_brl(centavos):
    """Format centavos as BRL string: 285000 -> 'R$ 2.850,00'"""
    try:
        return _format_brl(int(centavos))
    except (ValueError, TypeError):
        return "R$ 0,00"


@register.filter
def centavos_to_brl_input(centavos):
    """Convert centavos to BRL input format: 285000 -> '2850,00'"""
    try:
        centavos = int(centavos)
    except (ValueError, TypeError):
        return "0,00"
    reais = centavos / 100
    formatted = f"{reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return formatted
