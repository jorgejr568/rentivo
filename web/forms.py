from __future__ import annotations


def parse_brl(text: str) -> int | None:
    """Parse a BRL amount string into centavos. Returns None on invalid input.

    Accepts formats like '2850', '2850.00', '2.850,00', '2850,50'.
    """
    text = text.strip()
    if not text:
        return None
    # Handle PT-BR format: '2.850,00' -> '2850.00'
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return int(round(float(text) * 100))
    except ValueError:
        return None


def parse_formset(form_data: dict, prefix: str) -> list[dict[str, str]]:
    """Parse a Django-style formset from form data.

    Expects keys like:
      {prefix}-TOTAL_FORMS, {prefix}-0-description, {prefix}-0-amount, etc.

    Returns a list of dicts, one per form row.
    """
    total_key = f"{prefix}-TOTAL_FORMS"
    total = int(form_data.get(total_key, "0"))
    rows: list[dict[str, str]] = []
    for i in range(total):
        row: dict[str, str] = {}
        row_prefix = f"{prefix}-{i}-"
        for key, value in form_data.items():
            if key.startswith(row_prefix):
                field = key[len(row_prefix):]
                row[field] = value
        if row:
            rows.append(row)
    return rows
