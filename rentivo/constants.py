from zoneinfo import ZoneInfo

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


def format_month(ref: str) -> str:
    if not ref or "-" not in ref:
        return ref or ""
    year, month = ref.split("-")
    return f"{MONTHS_PT.get(month, month)}/{year}"
