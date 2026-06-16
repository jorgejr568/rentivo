from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from fpdf import FPDF

from rentivo.constants import format_month
from rentivo.models import format_brl
from rentivo.models.bill import Bill
from rentivo.observability import traced
from rentivo.pdf.invoice import _derive_colors

if TYPE_CHECKING:
    from rentivo.models.theme import Theme

logger = structlog.get_logger(__name__)

FONTS_DIR = Path(__file__).parent / "fonts"

# Success green is fixed (not theme-derived): the badge must read as "paid"
# regardless of the billing's theme palette.
_SUCCESS_GREEN = (22, 150, 95)


class ReciboPDF:
    @traced("pdf.generate_recibo")
    def generate(
        self,
        bill: Bill,
        billing_name: str,
        payer_name: str,
        issuer_name: str,
        payment_date: str,
        theme: Theme | None = None,
    ) -> bytes:
        from rentivo.models.theme import AVAILABLE_FONTS, DEFAULT_THEME

        theme = theme or DEFAULT_THEME
        self._colors = _derive_colors(theme)

        header_info = AVAILABLE_FONTS.get(theme.header_font, AVAILABLE_FONTS["Montserrat"])
        text_info = AVAILABLE_FONTS.get(theme.text_font, AVAILABLE_FONTS["Montserrat"])

        self._hf = theme.header_font.replace(" ", "")
        self._tf = theme.text_font.replace(" ", "")

        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=20)

        pdf.add_font(self._hf, "", str(FONTS_DIR / header_info["regular"]))
        pdf.add_font(self._hf, "B", str(FONTS_DIR / header_info["bold"]))
        if self._tf != self._hf:
            pdf.add_font(self._tf, "", str(FONTS_DIR / text_info["regular"]))
            pdf.add_font(self._tf, "B", str(FONTS_DIR / text_info["bold"]))

        page_w = pdf.w - pdf.l_margin - pdf.r_margin

        rows: list[tuple[str, str]] = []
        if issuer_name:
            rows.append(("Emitente", issuer_name))
        rows.append(("Pagador", payer_name))
        rows.append(("Referência", f"{billing_name} — {format_month(bill.reference_month)}"))
        if payment_date:
            rows.append(("Data do pagamento", payment_date))

        self._draw_header(pdf, page_w)
        self._draw_success_badge(pdf, page_w)
        self._draw_details_table(pdf, page_w, rows)
        self._draw_amount_box(pdf, page_w, bill.total_amount)
        self._draw_footer(pdf, page_w)

        output = pdf.output()
        logger.debug(
            "recibo_generated",
            billing_name=billing_name,
            total_centavos=bill.total_amount,
            bytes=len(output),
        )
        return output

    def _draw_header(self, pdf: FPDF, page_w: float) -> None:
        c = self._colors
        x = pdf.l_margin
        y = pdf.get_y()

        pdf.set_fill_color(*c["primary"])
        pdf.rect(x, y, page_w, 40, "F")

        pdf.set_y(y + 10)
        pdf.set_text_color(*c["text_contrast"])
        pdf.set_font(self._hf, "B", 26)
        pdf.cell(0, 14, "RECIBO DE PAGAMENTO", align="C", new_x="LMARGIN", new_y="NEXT")

        pdf.set_font(self._tf, "", 9)
        pdf.set_text_color(210, 195, 215)
        pdf.cell(0, 8, "Comprovante de quitação", align="C", new_x="LMARGIN", new_y="NEXT")

        pdf.set_y(y + 40 + 14)

    def _draw_success_badge(self, pdf: FPDF, page_w: float) -> None:
        """A green circle with a white check + 'PAGAMENTO CONFIRMADO' label."""
        cx = pdf.l_margin + page_w / 2
        y = pdf.get_y() + 2
        r = 9.0

        pdf.set_fill_color(*_SUCCESS_GREEN)
        pdf.ellipse(cx - r, y, r * 2, r * 2, style="F")

        cy = y + r
        pdf.set_draw_color(255, 255, 255)
        pdf.set_line_width(1.6)
        pdf.line(cx - 4.2, cy + 0.4, cx - 1.4, cy + 3.6)
        pdf.line(cx - 1.4, cy + 3.6, cx + 4.6, cy - 3.4)
        pdf.set_line_width(0.2)

        pdf.set_xy(pdf.l_margin, y + r * 2 + 4)
        pdf.set_font(self._hf, "B", 11)
        pdf.set_text_color(*_SUCCESS_GREEN)
        pdf.cell(page_w, 7, "PAGAMENTO CONFIRMADO", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(9)

    def _draw_details_table(self, pdf: FPDF, page_w: float, rows: list[tuple[str, str]]) -> None:
        c = self._colors
        x = pdf.l_margin
        row_h = 12.0
        label_w = 58.0
        start_y = pdf.get_y()

        for i, (label, value) in enumerate(rows):
            y = pdf.get_y()
            if i % 2 == 1:
                pdf.set_fill_color(*c["row_alt"])
                pdf.rect(x, y, page_w, row_h, "F")
            pdf.set_xy(x + 5, y)
            pdf.set_font(self._tf, "", 9)
            pdf.set_text_color(*c["muted_text"])
            pdf.cell(label_w, row_h, label.upper())
            pdf.set_xy(x + label_w, y)
            pdf.set_font(self._tf, "B", 11)
            pdf.set_text_color(*c["text_color"])
            pdf.cell(page_w - label_w - 5, row_h, value)
            pdf.set_y(y + row_h)

        pdf.set_draw_color(*c["border_color"])
        pdf.set_line_width(0.3)
        pdf.rect(x, start_y, page_w, row_h * len(rows))
        pdf.set_line_width(0.2)

    def _draw_amount_box(self, pdf: FPDF, page_w: float, total_centavos: int) -> None:
        """The amount received, anchored near the bottom of the page."""
        c = self._colors
        x = pdf.l_margin
        box_h = 28.0
        y = pdf.h - pdf.b_margin - box_h - 14

        pdf.set_fill_color(*c["secondary_dark"])
        pdf.rect(x, y, page_w, box_h, "F")
        pdf.set_xy(x + 12, y + 6)
        pdf.set_font(self._tf, "", 9)
        pdf.set_text_color(190, 222, 222)
        pdf.cell(0, 5, "VALOR RECEBIDO")
        pdf.set_xy(x + 12, y + 13)
        pdf.set_font(self._hf, "B", 24)
        pdf.set_text_color(*c["text_contrast"])
        pdf.cell(0, 13, format_brl(total_centavos))

    def _draw_footer(self, pdf: FPDF, page_w: float) -> None:
        c = self._colors
        pdf.set_y(-18)
        pdf.set_draw_color(*c["border_color"])
        pdf.set_line_width(0.3)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.l_margin + page_w, y)
        pdf.ln(4)
        pdf.set_font(self._tf, "", 7)
        pdf.set_text_color(*c["muted_text"])
        pdf.cell(0, 5, "Documento gerado automaticamente", align="C")
