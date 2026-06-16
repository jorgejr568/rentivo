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

        self._draw_header(pdf, page_w)
        self._draw_body(pdf, page_w, bill, billing_name, payer_name, payment_date)
        self._draw_issuer(pdf, page_w, issuer_name)
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

        pdf.set_y(y + 40 + 16)

    def _draw_body(
        self,
        pdf: FPDF,
        page_w: float,
        bill: Bill,
        billing_name: str,
        payer_name: str,
        payment_date: str,
    ) -> None:
        c = self._colors
        x = pdf.l_margin

        # Amount card
        card_h = 26
        card_y = pdf.get_y()
        pdf.set_fill_color(*c["secondary_dark"])
        pdf.rect(x, card_y, page_w, card_h, "F")
        pdf.set_xy(x + 10, card_y + 4)
        pdf.set_font(self._tf, "", 8)
        pdf.set_text_color(180, 220, 220)
        pdf.cell(0, 5, "VALOR RECEBIDO")
        pdf.set_xy(x + 10, card_y + 11)
        pdf.set_font(self._hf, "B", 20)
        pdf.set_text_color(*c["text_contrast"])
        pdf.cell(0, 12, format_brl(bill.total_amount))
        pdf.set_y(card_y + card_h + 14)

        # Acknowledgement paragraph
        pdf.set_font(self._tf, "", 11)
        pdf.set_text_color(*c["text_color"])
        body = (
            f"Recebemos de {payer_name} a importância de {format_brl(bill.total_amount)} "
            f"referente a {billing_name} — {format_month(bill.reference_month)}."
        )
        pdf.multi_cell(page_w, 7, body)
        pdf.ln(8)

        if payment_date:
            pdf.set_font(self._tf, "B", 10)
            pdf.set_text_color(*c["muted_text"])
            pdf.cell(0, 6, f"Data do pagamento: {payment_date}", new_x="LMARGIN", new_y="NEXT")

    def _draw_issuer(self, pdf: FPDF, page_w: float, issuer_name: str) -> None:
        if not issuer_name:
            return
        c = self._colors
        pdf.ln(18)
        pdf.set_font(self._tf, "", 9)
        pdf.set_text_color(*c["muted_text"])
        pdf.cell(0, 6, "EMITENTE", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        pdf.set_font(self._tf, "B", 12)
        pdf.set_text_color(*c["text_color"])
        pdf.cell(0, 8, issuer_name, new_x="LMARGIN", new_y="NEXT")

    def _draw_footer(self, pdf: FPDF, page_w: float) -> None:
        c = self._colors
        pdf.set_y(-30)
        pdf.set_draw_color(*c["border_color"])
        pdf.set_line_width(0.3)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.l_margin + page_w, y)
        pdf.ln(5)
        pdf.set_font(self._tf, "", 7)
        pdf.set_text_color(*c["muted_text"])
        pdf.cell(0, 5, "Documento gerado automaticamente", align="C")
