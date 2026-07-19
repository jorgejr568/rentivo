from __future__ import annotations

from dataclasses import dataclass

from rentivo.models import parse_brl as parse_brl  # noqa: F401 — re-export
from rentivo.models.billing import ItemType


def safe_redirect_path(raw: str, fallback: str) -> str:
    """Return a user-supplied redirect target only if it's a same-origin relative path.

    Rejects absolute URLs (\"https://evil\"), protocol-relative URLs (\"//evil\"),
    and backslash-prefixed paths that some browsers normalize to the root.
    """
    candidate = (raw or "").strip()
    if not candidate.startswith("/"):
        return fallback
    if candidate.startswith("//") or candidate.startswith("/\\") or candidate.startswith("/%2f"):
        return fallback
    return candidate


def parse_formset(form_data: dict, prefix: str) -> list[dict[str, str]]:
    """Parse a Django-style formset from form data.

    Expects keys like:
      {prefix}-TOTAL_FORMS, {prefix}-0-description, {prefix}-0-amount, etc.

    Returns a list of dicts, one per form row.
    """
    total_key = f"{prefix}-TOTAL_FORMS"
    try:
        total = int(form_data.get(total_key, "0"))
    except ValueError, TypeError:
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


@dataclass(frozen=True)
class ParsedLineItem:
    """One validated line-item row parsed from a formset.

    ``index`` is the row's position in the submitted formset (post
    ``parse_formset`` filtering) so callers can preserve sort order even
    when blank rows are skipped.
    """

    index: int
    description: str
    amount: int  # centavos
    item_type: ItemType
    uuid: str | None = None


def parse_line_items(
    form_data: dict,
    prefix: str,
    *,
    amount_only_for_fixed: bool = False,
) -> list[ParsedLineItem]:
    """Parse a line-item formset (description / amount / item_type rows).

    Rows with a blank description are skipped. Unknown ``item_type`` values
    fall back to ``ItemType.FIXED``. Invalid or missing amounts become 0.
    With ``amount_only_for_fixed=True`` (billing items), non-FIXED rows get
    amount 0 regardless of input — variable amounts are entered at bill
    generation time, not on the billing.
    """
    items: list[ParsedLineItem] = []
    for i, row in enumerate(parse_formset(form_data, prefix)):
        description = row.get("description", "").strip()
        if not description:
            continue
        try:
            item_type = ItemType(row.get("item_type", "fixed"))
        except ValueError:
            item_type = ItemType.FIXED
        if amount_only_for_fixed and item_type != ItemType.FIXED:
            amount = 0
        else:
            amount = parse_brl(row.get("amount", "")) or 0
        items.append(
            ParsedLineItem(
                index=i,
                description=description,
                amount=amount,
                item_type=item_type,
                uuid=row.get("uuid", "").strip() or None,
            )
        )
    return items


def parse_extras(form_data: dict, prefix: str = "extras") -> list[tuple[str, int]]:
    """Parse an extras formset into (description, amount_centavos) tuples.

    Rows with a blank description or a non-positive/invalid amount are
    skipped — extras must carry a positive amount.
    """
    extras: list[tuple[str, int]] = []
    for row in parse_formset(form_data, prefix):
        description = row.get("description", "").strip()
        amount = parse_brl(row.get("amount", ""))
        if description and amount and amount > 0:
            extras.append((description, amount))
    return extras
