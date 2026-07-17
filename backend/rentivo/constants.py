from zoneinfo import ZoneInfo

from rentivo.models.bill import BillStatus
from rentivo.models.billing import ItemType

SP_TZ = ZoneInfo("America/Sao_Paulo")

MONTHS_PT = {
    "01": "Janeiro",
    "02": "Fevereiro",
    "03": "Março",
    "04": "Abril",
    "05": "Maio",
    "06": "Junho",
    "07": "Julho",
    "08": "Agosto",
    "09": "Setembro",
    "10": "Outubro",
    "11": "Novembro",
    "12": "Dezembro",
}

TYPE_LABELS = {ItemType.FIXED: "Fixo", ItemType.VARIABLE: "Variável", ItemType.EXTRA: "Extra"}

STATUS_LABELS = {
    BillStatus.DRAFT: "Rascunho",
    BillStatus.PUBLISHED: "Publicado",
    BillStatus.SENT: "Enviado",
    BillStatus.PAID: "Pago",
    BillStatus.CANCELLED: "Cancelado",
    BillStatus.DELAYED_PAYMENT: "Pag. Atrasado",
}


def split_month_ref(ref: str) -> tuple[str, str] | None:
    """Split a ``YYYY-MM`` reference into ``(year, month)`` parts.

    Returns ``None`` when ``ref`` is empty or not ``-``-separated, so callers
    can apply their own passthrough. The month is everything after the first
    ``-`` (so a stray ``YYYY-MM-DD`` degrades gracefully instead of raising).
    """
    if not ref or "-" not in ref:
        return None
    year, _, month = ref.partition("-")
    return year, month


def format_month(ref: str) -> str:
    parts = split_month_ref(ref)
    if parts is None:
        return ref or ""
    year, month = parts
    return f"{MONTHS_PT.get(month, month)}/{year}"
