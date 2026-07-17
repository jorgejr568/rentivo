from __future__ import annotations

from rentivo.communications.render import month_long, render_markdown, substitute


def test_render_markdown_paragraphs():
    html = render_markdown("Prezado João,\n\nSegue a cobrança.")
    assert "<p>Prezado João,</p>" in html
    assert "<p>Segue a cobrança.</p>" in html


def test_render_markdown_strips_raw_html():
    html = render_markdown("Oi <script>alert('x')</script> **fim**")
    # Raw HTML is rendered inert (escaped), never emitted as a live tag.
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<strong>fim</strong>" in html


def test_substitute_replaces_known_tokens_with_and_without_spaces():
    out = substitute(
        "Olá {{tenant_name}}, unidade {{ unit }}.",
        {"tenant_name": "João", "unit": "Joy 105"},
    )
    assert out == "Olá João, unidade Joy 105."


def test_substitute_leaves_unknown_tokens_untouched():
    out = substitute("Olá {{tenant_name}} {{mystery}}", {"tenant_name": "Ana"})
    assert out == "Olá Ana {{mystery}}"


def test_substitute_treats_none_value_as_empty():
    out = substitute("Venc.: {{due_date}}", {"due_date": None})
    assert out == "Venc.: "


def test_month_long_pt_br():
    assert month_long("2026-05") == "maio de 2026"


def test_month_long_passthrough_on_bad_input():
    assert month_long("") == ""
    assert month_long("garbage") == "garbage"


def test_month_long_passthrough_on_unknown_month():
    # Hyphenated but the month part is not a known key, so it is returned as-is.
    assert month_long("2026-13") == "2026-13"
