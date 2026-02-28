from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from fpdf import FPDF

from rentivo.constants import TYPE_LABELS, format_month
from rentivo.models import format_brl
from rentivo.models.bill import Bill

if TYPE_CHECKING:
    from rentivo.models.theme import Theme

logger = logging.getLogger(__name__)

FONTS_DIR = Path(__file__).parent / "fonts"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _derive_colors(theme: Theme) -> dict[str, tuple[int, int, int]]:
    primary = _hex_to_rgb(theme.primary)
    primary_light = _hex_to_rgb(theme.primary_light)
    secondary = _hex_to_rgb(theme.secondary)
    secondary_dark = _hex_to_rgb(theme.secondary_dark)
    text_color = _hex_to_rgb(theme.text_color)
    text_contrast = _hex_to_rgb(theme.text_contrast)

    row_alt = tuple(min(255, c + 6) for c in primary_light)
    border_color = tuple(max(0, c - 28) for c in primary_light)
    muted_text = tuple(min(255, c + 68) for c in text_color)

    return {
        "primary": primary,
        "primary_light": primary_light,
        "secondary": secondary,
        "secondary_dark": secondary_dark,
        "text_color": text_color,
        "text_contrast": text_contrast,
        "muted_text": muted_text,
        "row_alt": row_alt,  # type: ignore[dict-item]
        "border_color": border_color,  # type: ignore[dict-item]
    }


class InvoicePDF:
    def generate(
        self,
        bill: Bill,
        billing_name: str,
        pix_qrcode_png: bytes | None = None,
        pix_key: str = "",
        pix_payload: str = "",
        theme: Theme | None = None,
    ) -> bytes:
        from rentivo.models.theme import AVAILABLE_FONTS, DEFAULT_THEME

        theme = theme or DEFAULT_THEME
        self._colors = _derive_colors(theme)

        # Resolve font families
        header_info = AVAILABLE_FONTS.get(theme.header_font, AVAILABLE_FONTS["Montserrat"])
        text_info = AVAILABLE_FONTS.get(theme.text_font, AVAILABLE_FONTS["Montserrat"])

        self._hf = theme.header_font.replace(" ", "")
        self._hf_sb = self._hf + "SB"
        self._tf = theme.text_font.replace(" ", "")
        self._tf_sb = self._tf + "SB"

        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=20)

        # Register header font
        pdf.add_font(self._hf, "", str(FONTS_DIR / header_info["regular"]))
        pdf.add_font(self._hf, "B", str(FONTS_DIR / header_info["bold"]))
        pdf.add_font(self._hf_sb, "", str(FONTS_DIR / header_info["semibold"]))

        # Register text font if different
        if self._tf != self._hf:
            pdf.add_font(self._tf, "", str(FONTS_DIR / text_info["regular"]))
            pdf.add_font(self._tf, "B", str(FONTS_DIR / text_info["bold"]))
            pdf.add_font(self._tf_sb, "", str(FONTS_DIR / text_info["semibold"]))
        else:
            self._tf_sb = self._hf_sb

        page_w = pdf.w - pdf.l_margin - pdf.r_margin

        self._draw_header(pdf, page_w, billing_name, bill.reference_month, bill.due_date)
        self._draw_table(pdf, page_w, bill)
        self._draw_total(pdf, page_w, bill.total_amount)

        if bill.notes:
            self._draw_notes(pdf, page_w, bill.notes)

        self._draw_footer(pdf, page_w)

        if pix_qrcode_png:
            pdf.add_page()
            self._draw_pix_page(pdf, page_w, pix_qrcode_png, bill.total_amount, pix_key, pix_payload)
            self._draw_footer(pdf, page_w)

        output = pdf.output()
        logger.debug(
            "PDF generated: billing=%s items=%d pix=%s size=%d bytes",
            billing_name,
            len(bill.line_items),
            bool(pix_qrcode_png),
            len(output),
        )
        return output

    def _draw_info_card(
        self,
        pdf: FPDF,
        x: float,
        y: float,
        w: float,
        h: float,
        label: str,
        value: str,
    ) -> None:
        """Draw a single info card with accent bar, label, and value."""
        c = self._colors
        pdf.set_fill_color(*c["primary_light"])
        pdf.rect(x, y, w, h, "F")
        pdf.set_fill_color(*c["secondary_dark"])
        pdf.rect(x, y, 3, h, "F")

        pdf.set_xy(x + 10, y + 3)
        pdf.set_font(self._tf_sb, "", 7)
        pdf.set_text_color(*c["muted_text"])
        pdf.cell(w - 14, 5, label, new_x="LEFT", new_y="NEXT")
        pdf.set_x(x + 10)
        pdf.set_font(self._tf, "B", 13)
        pdf.set_text_color(*c["text_color"])
        pdf.cell(w - 14, 9, value)

    def _draw_header(
        self,
        pdf: FPDF,
        page_w: float,
        billing_name: str,
        reference_month: str,
        due_date: str | None = None,
    ) -> None:
        c = self._colors
        x = pdf.l_margin
        y = pdf.get_y()

        # Header banner
        pdf.set_fill_color(*c["primary"])
        pdf.rect(x, y, page_w, 40, "F")

        # Title
        pdf.set_y(y + 10)
        pdf.set_text_color(*c["text_contrast"])
        pdf.set_font(self._hf, "B", 28)
        pdf.cell(0, 14, "FATURA", align="C", new_x="LMARGIN", new_y="NEXT")

        pdf.set_font(self._tf, "", 9)
        pdf.set_text_color(210, 195, 215)
        pdf.cell(
            0,
            8,
            "Documento de cobran\u00e7a",
            align="C",
            new_x="LMARGIN",
            new_y="NEXT",
        )

        pdf.ln(10)

        # Info cards
        pdf.set_text_color(*c["text_color"])
        card_h = 24
        card_y = pdf.get_y()

        if due_date:
            self._draw_info_card(pdf, x, card_y, page_w, card_h, "COBRAN\u00c7A", billing_name)

            row2_y = card_y + card_h + 6
            card_w = page_w / 2 - 3
            self._draw_info_card(
                pdf,
                x,
                row2_y,
                card_w,
                card_h,
                "REFER\u00caNCIA",
                format_month(reference_month),
            )
            self._draw_info_card(pdf, x + card_w + 6, row2_y, card_w, card_h, "VENCIMENTO", due_date)
            card_y = row2_y
        else:
            card_w = page_w / 2 - 3
            self._draw_info_card(pdf, x, card_y, card_w, card_h, "COBRAN\u00c7A", billing_name)
            self._draw_info_card(
                pdf,
                x + card_w + 6,
                card_y,
                card_w,
                card_h,
                "REFER\u00caNCIA",
                format_month(reference_month),
            )

        pdf.set_y(card_y + card_h + 14)

    def _draw_table(self, pdf: FPDF, page_w: float, bill: Bill) -> None:
        c = self._colors
        col_desc = page_w * 0.50
        col_type = page_w * 0.22
        col_amount = page_w * 0.28
        line_h = 11

        # Section label
        pdf.set_font(self._hf, "B", 11)
        pdf.set_text_color(*c["primary"])
        pdf.cell(0, 8, "ITENS DA FATURA", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Accent underline
        pdf.set_draw_color(*c["secondary"])
        pdf.set_line_width(0.8)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.l_margin + 30, y)
        pdf.ln(6)

        # Table header
        pdf.set_fill_color(*c["primary"])
        pdf.set_text_color(*c["text_contrast"])
        pdf.set_font(self._tf_sb, "", 9)

        pdf.cell(col_desc, line_h, "  Descri\u00e7\u00e3o", border=0, fill=True)
        pdf.cell(col_type, line_h, "Tipo", border=0, fill=True, align="C")
        pdf.cell(
            col_amount,
            line_h,
            "Valor  ",
            border=0,
            fill=True,
            align="R",
            new_x="LMARGIN",
            new_y="NEXT",
        )

        # Table rows
        pdf.set_text_color(*c["text_color"])
        pdf.set_font(self._tf, "", 10)

        for i, item in enumerate(bill.line_items):
            if i % 2 == 0:
                pdf.set_fill_color(*c["row_alt"])
            else:
                pdf.set_fill_color(*c["text_contrast"])

            pdf.cell(col_desc, line_h, f"  {item.description}", border=0, fill=True)

            type_label = TYPE_LABELS.get(item.item_type, item.item_type)
            pdf.set_font(self._tf, "", 9)
            pdf.cell(col_type, line_h, type_label, border=0, fill=True, align="C")
            pdf.set_font(self._tf_sb, "", 10)
            pdf.cell(
                col_amount,
                line_h,
                f"{format_brl(item.amount)}  ",
                border=0,
                fill=True,
                align="R",
                new_x="LMARGIN",
                new_y="NEXT",
            )
            pdf.set_font(self._tf, "", 10)

        # Bottom border
        pdf.set_draw_color(*c["border_color"])
        pdf.set_line_width(0.3)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.l_margin + page_w, y)

    def _draw_total(self, pdf: FPDF, page_w: float, total_amount: int) -> None:
        c = self._colors
        pdf.ln(4)

        col_label = page_w * 0.72
        col_amount = page_w * 0.28
        total_h = 14

        pdf.set_fill_color(*c["secondary_dark"])
        pdf.set_text_color(*c["text_contrast"])
        pdf.set_font(self._tf_sb, "", 12)
        pdf.cell(col_label, total_h, "TOTAL  ", border=0, fill=True, align="R")
        pdf.set_font(self._hf, "B", 14)
        pdf.cell(
            col_amount,
            total_h,
            f"{format_brl(total_amount)}  ",
            border=0,
            fill=True,
            align="R",
            new_x="LMARGIN",
            new_y="NEXT",
        )

    def _draw_notes(self, pdf: FPDF, page_w: float, notes: str) -> None:
        c = self._colors
        pdf.ln(14)

        pdf.set_font(self._tf_sb, "", 8)
        pdf.set_text_color(*c["muted_text"])
        pdf.cell(0, 6, "OBSERVA\u00c7\u00d5ES", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        x = pdf.l_margin
        y = pdf.get_y()

        pdf.set_fill_color(*c["secondary"])
        pdf.rect(x, y, 3, 20, "F")
        pdf.set_fill_color(*c["primary_light"])
        pdf.rect(x + 3, y, page_w - 3, 20, "F")
        pdf.set_xy(x + 12, y + 6)
        pdf.set_text_color(*c["text_color"])
        pdf.set_font(self._tf, "", 10)
        pdf.multi_cell(page_w - 18, 6, notes)

    def _draw_pix_page(
        self,
        pdf: FPDF,
        page_w: float,
        qrcode_png: bytes,
        total_amount: int,
        pix_key: str,
        pix_payload: str,
    ) -> None:
        c = self._colors
        x = pdf.l_margin

        # Header banner
        y = pdf.get_y()
        pdf.set_fill_color(*c["primary"])
        pdf.rect(x, y, page_w, 30, "F")

        pdf.set_y(y + 8)
        pdf.set_text_color(*c["text_contrast"])
        pdf.set_font(self._hf, "B", 22)
        pdf.cell(0, 12, "PAGAMENTO VIA PIX", align="C", new_x="LMARGIN", new_y="NEXT")

        pdf.ln(16)

        # QR code
        qr_size = 55
        qr_x = x + (page_w - qr_size) / 2
        qr_y = pdf.get_y()

        buf = BytesIO(qrcode_png)
        pdf.image(buf, x=qr_x, y=qr_y, w=qr_size, h=qr_size)
        pdf.set_y(qr_y + qr_size + 6)

        # Instruction text
        pdf.set_font(self._tf, "", 10)
        pdf.set_text_color(*c["muted_text"])
        pdf.cell(
            0,
            6,
            "Escaneie o QR Code ou copie o c\u00f3digo abaixo",
            align="C",
            new_x="LMARGIN",
            new_y="NEXT",
        )

        pdf.ln(10)

        # Amount card
        card_h = 22
        card_y = pdf.get_y()
        pdf.set_fill_color(*c["secondary_dark"])
        pdf.rect(x, card_y, page_w, card_h, "F")

        pdf.set_xy(x + 10, card_y + 3)
        pdf.set_font(self._tf_sb, "", 8)
        pdf.set_text_color(180, 220, 220)
        pdf.cell(0, 5, "VALOR A PAGAR")
        pdf.set_xy(x + 10, card_y + 10)
        pdf.set_font(self._hf, "B", 18)
        pdf.set_text_color(*c["text_contrast"])
        pdf.cell(0, 10, format_brl(total_amount))

        pdf.set_y(card_y + card_h + 12)

        # PIX key info card
        if pix_key:
            pdf.set_font(self._tf_sb, "", 8)
            pdf.set_text_color(*c["muted_text"])
            pdf.cell(0, 5, "CHAVE PIX", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

            key_y = pdf.get_y()
            key_h = 14
            pdf.set_fill_color(*c["primary_light"])
            pdf.rect(x, key_y, page_w, key_h, "F")
            pdf.set_fill_color(*c["secondary_dark"])
            pdf.rect(x, key_y, 3, key_h, "F")

            pdf.set_xy(x + 10, key_y + 3)
            pdf.set_font(self._tf, "B", 11)
            pdf.set_text_color(*c["text_color"])
            pdf.cell(0, 8, pix_key)

            pdf.set_y(key_y + key_h + 10)

        # Pix Copia e Cola
        if pix_payload:
            pdf.set_font(self._tf_sb, "", 8)
            pdf.set_text_color(*c["muted_text"])
            pdf.cell(0, 5, "PIX COPIA E COLA", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

            payload_y = pdf.get_y()
            payload_cell_w = page_w - 12

            pdf.set_font(self._tf, "", 7)
            result = pdf.multi_cell(payload_cell_w, 4, pix_payload, dry_run=True, output="LINES")
            text_h = len(result) * 4
            payload_h = text_h + 8

            pdf.set_fill_color(*c["row_alt"])
            pdf.rect(x, payload_y, page_w, payload_h, "F")
            pdf.set_draw_color(*c["border_color"])
            pdf.set_line_width(0.3)
            pdf.rect(x, payload_y, page_w, payload_h, "D")

            pdf.set_xy(x + 6, payload_y + 4)
            pdf.set_font(self._tf, "", 7)
            pdf.set_text_color(*c["text_color"])
            pdf.multi_cell(payload_cell_w, 4, pix_payload)

            pdf.set_y(payload_y + payload_h + 4)

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
