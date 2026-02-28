from __future__ import annotations

from rentivo.models import parse_brl as parse_brl  # noqa: F401 — re-export


def parse_formset(form_data: dict, prefix: str) -> list[dict[str, str]]:
    """Parse a Django-style formset from form data.

    Expects keys like:
      {prefix}-TOTAL_FORMS, {prefix}-0-description, {prefix}-0-amount, etc.

    Returns a list of dicts, one per form row.
    """
    total_key = f"{prefix}-TOTAL_FORMS"
    try:
        total = int(form_data.get(total_key, "0"))
    except (ValueError, TypeError):
        total = 0
    rows: list[dict[str, str]] = []
    for i in range(total):
        row: dict[str, str] = {}
        row_prefix = f"{prefix}-{i}-"
        for key, value in form_data.items():
            if key.startswith(row_prefix):
                field = key[len(row_prefix) :]
                row[field] = value
        if row:
            rows.append(row)
    return rows
