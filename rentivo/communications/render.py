"""Injection-safe Markdown rendering and placeholder substitution for tenant
communications.

User-authored bodies are Markdown. ``render_markdown`` runs markdown-it-py
with raw HTML *disabled*, so any ``<tag>`` in the source is escaped to inert
text — there is no path from user input to live HTML.
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

from rentivo.constants import MONTHS_PT, split_month_ref

# commonmark preset, but raw HTML explicitly disabled: the commonmark preset
# turns html on, so we override it to keep any <tag> in the source escaped
# (rendered as inert text, never passed through as a live tag).
_md = MarkdownIt("commonmark", {"html": False})

# Matches {{ key }} with optional surrounding whitespace; key is a bare identifier.
_TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render_markdown(text: str) -> str:
    """Render Markdown to safe HTML (raw HTML in the source is escaped)."""
    return _md.render(text or "")


def substitute(text: str, mapping: dict[str, str | None]) -> str:
    """Replace ``{{key}}`` tokens from ``mapping``; unknown tokens stay verbatim.

    A ``None`` value renders as an empty string.
    """

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in mapping:
            return match.group(0)
        value = mapping[key]
        return "" if value is None else str(value)

    return _TOKEN.sub(repl, text or "")


def month_long(ref: str) -> str:
    """Format a ``YYYY-MM`` reference as e.g. ``maio de 2026``.

    Returns the input unchanged when it is empty or not ``YYYY-MM`` shaped.
    """
    parts = split_month_ref(ref)
    if parts is None:
        return ref or ""
    year, month = parts
    name = MONTHS_PT.get(month)
    if name is None:
        return ref
    return f"{name.lower()} de {year}"
