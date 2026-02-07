from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fpdf import FPDF

from billing.models import format_brl
from billing.models.bill import Bill

FONTS_DIR = Path(__file__).parent / "fonts"

MONTHS_PT = {
    "01": "Janeiro",
    "02": "Fevereiro",
    "03": "Mar\u00e7o",
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

TYPE_LABELS = {
    "fixed": "Fixo",
    "variable": "Vari\u00e1vel",
    "extra": "Extra",
}

# Color palette — derived from joy-purple / joy-teal / joy-teal-dark
PURPLE = (138, 76, 148)
PURPLE_LIGHT = (238, 228, 241)
TEAL = (110, 175, 174)
TEAL_DARK = (53, 123, 124)
WHITE = (255, 255, 255)
DARK_TEXT = (40, 40, 48)
MUTED_TEXT = (108, 108, 120)
ROW_ALT = (244, 240, 246)
BORDER_COLOR = (210, 200, 215)


def _format_month(ref: str) -> str:
    year, month = ref.split("-")
    return f"{MONTHS_PT.get(month, month)}/{year}"


class InvoicePDF:
    def generate(
        self,
        bill: Bill,
        billing_name: str,
        pix_qrcode_png: bytes | None = None,
        pix_key: str = "",
        pix_payload: str = "",
    ) -> bytes:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=20)

        # Register Montserrat font family
        pdf.add_font("Montserrat", "", str(FONTS_DIR / "Montserrat-Regular.ttf"))
        pdf.add_font("Montserrat", "B", str(FONTS_DIR / "Montserrat-Bold.ttf"))
        pdf.add_font("MontserratSB", "", str(FONTS_DIR / "Montserrat-SemiBold.ttf"))

        page_w = pdf.w - pdf.l_margin - pdf.r_margin

        self._draw_header(pdf, page_w, billing_name, bill.reference_month)
        self._draw_table(pdf, page_w, bill)
        self._draw_total(pdf, page_w, bill.total_amount)

        if bill.notes:
            self._draw_notes(pdf, page_w, bill.notes)

        self._draw_footer(pdf, page_w)

        if pix_qrcode_png:
            pdf.add_page()
            self._draw_pix_page(
                pdf, page_w, pix_qrcode_png, bill.total_amount, pix_key, pix_payload
            )
            self._draw_footer(pdf, page_w)

        return pdf.output()

    def _draw_header(
        self, pdf: FPDF, page_w: float, billing_name: str, reference_month: str
    ) -> None:
        x = pdf.l_margin
        y = pdf.get_y()

        # Header banner — purple
        pdf.set_fill_color(*PURPLE)
        pdf.rect(x, y, page_w, 40, "F")

        # Title
        pdf.set_y(y + 10)
        pdf.set_text_color(*WHITE)
        pdf.set_font("Montserrat", "B", 28)
        pdf.cell(0, 14, "FATURA", align="C", new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("Montserrat", "", 9)
        pdf.set_text_color(210, 195, 215)
        pdf.cell(
            0, 8, "Documento de cobran\u00e7a", align="C",
            new_x="LMARGIN", new_y="NEXT",
        )

        pdf.ln(10)

        # Info cards
        pdf.set_text_color(*DARK_TEXT)
        card_w = page_w / 2 - 3
        card_h = 24
        card_y = pdf.get_y()

        # Left card — billing name
        pdf.set_fill_color(*PURPLE_LIGHT)
        pdf.rect(x, card_y, card_w, card_h, "F")
        # Left accent strip
        pdf.set_fill_color(*TEAL_DARK)
        pdf.rect(x, card_y, 3, card_h, "F")

        pdf.set_xy(x + 10, card_y + 3)
        pdf.set_font("MontserratSB", "", 7)
        pdf.set_text_color(*MUTED_TEXT)
        pdf.cell(card_w - 14, 5, "COBRAN\u00c7A", new_x="LEFT", new_y="NEXT")
        pdf.set_x(x + 10)
        pdf.set_font("Montserrat", "B", 13)
        pdf.set_text_color(*DARK_TEXT)
        pdf.cell(card_w - 14, 9, billing_name)

        # Right card — reference month
        right_x = x + card_w + 6
        pdf.set_fill_color(*PURPLE_LIGHT)
        pdf.rect(right_x, card_y, card_w, card_h, "F")
        pdf.set_fill_color(*TEAL_DARK)
        pdf.rect(right_x, card_y, 3, card_h, "F")

        pdf.set_xy(right_x + 10, card_y + 3)
        pdf.set_font("MontserratSB", "", 7)
        pdf.set_text_color(*MUTED_TEXT)
        pdf.cell(card_w - 14, 5, "REFER\u00caNCIA", new_x="LEFT", new_y="NEXT")
        pdf.set_x(right_x + 10)
        pdf.set_font("Montserrat", "B", 13)
        pdf.set_text_color(*DARK_TEXT)
        pdf.cell(card_w - 14, 9, _format_month(reference_month))

        pdf.set_y(card_y + card_h + 14)

    def _draw_table(self, pdf: FPDF, page_w: float, bill: Bill) -> None:
        col_desc = page_w * 0.50
        col_type = page_w * 0.22
        col_amount = page_w * 0.28
        line_h = 11

        # Section label
        pdf.set_font("Montserrat", "B", 11)
        pdf.set_text_color(*PURPLE)
        pdf.cell(0, 8, "ITENS DA FATURA", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Accent underline
        pdf.set_draw_color(*TEAL)
        pdf.set_line_width(0.8)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.l_margin + 30, y)
        pdf.ln(6)

        # Table header
        pdf.set_fill_color(*PURPLE)
        pdf.set_text_color(*WHITE)
        pdf.set_font("MontserratSB", "", 9)

        pdf.cell(col_desc, line_h, "  Descri\u00e7\u00e3o", border=0, fill=True)
        pdf.cell(col_type, line_h, "Tipo", border=0, fill=True, align="C")
        pdf.cell(
            col_amount, line_h, "Valor  ", border=0, fill=True, align="R",
            new_x="LMARGIN", new_y="NEXT",
        )

        # Table rows
        pdf.set_text_color(*DARK_TEXT)
        pdf.set_font("Montserrat", "", 10)

        for i, item in enumerate(bill.line_items):
            if i % 2 == 0:
                pdf.set_fill_color(*ROW_ALT)
            else:
                pdf.set_fill_color(*WHITE)

            pdf.cell(col_desc, line_h, f"  {item.description}", border=0, fill=True)

            type_label = TYPE_LABELS.get(item.item_type, item.item_type)
            pdf.set_font("Montserrat", "", 9)
            pdf.cell(col_type, line_h, type_label, border=0, fill=True, align="C")
            pdf.set_font("MontserratSB", "", 10)
            pdf.cell(
                col_amount, line_h, f"{format_brl(item.amount)}  ",
                border=0, fill=True, align="R",
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf.set_font("Montserrat", "", 10)

        # Bottom border
        pdf.set_draw_color(*BORDER_COLOR)
        pdf.set_line_width(0.3)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.l_margin + page_w, y)

    def _draw_total(self, pdf: FPDF, page_w: float, total_amount: int) -> None:
        pdf.ln(4)

        col_label = page_w * 0.72
        col_amount = page_w * 0.28
        total_h = 14

        # Total bar — teal dark
        pdf.set_fill_color(*TEAL_DARK)
        pdf.set_text_color(*WHITE)
        pdf.set_font("MontserratSB", "", 12)
        pdf.cell(col_label, total_h, "TOTAL  ", border=0, fill=True, align="R")
        pdf.set_font("Montserrat", "B", 14)
        pdf.cell(
            col_amount, total_h, f"{format_brl(total_amount)}  ",
            border=0, fill=True, align="R",
            new_x="LMARGIN", new_y="NEXT",
        )

    def _draw_notes(self, pdf: FPDF, page_w: float, notes: str) -> None:
        pdf.ln(14)

        pdf.set_font("MontserratSB", "", 8)
        pdf.set_text_color(*MUTED_TEXT)
        pdf.cell(0, 6, "OBSERVA\u00c7\u00d5ES", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        x = pdf.l_margin
        y = pdf.get_y()

        # Left accent bar
        pdf.set_fill_color(*TEAL)
        pdf.rect(x, y, 3, 20, "F")
        # Background
        pdf.set_fill_color(*PURPLE_LIGHT)
        pdf.rect(x + 3, y, page_w - 3, 20, "F")
        # Text
        pdf.set_xy(x + 12, y + 6)
        pdf.set_text_color(*DARK_TEXT)
        pdf.set_font("Montserrat", "", 10)
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
        x = pdf.l_margin

        # Header banner — purple (same style as page 1)
        y = pdf.get_y()
        pdf.set_fill_color(*PURPLE)
        pdf.rect(x, y, page_w, 30, "F")

        pdf.set_y(y + 8)
        pdf.set_text_color(*WHITE)
        pdf.set_font("Montserrat", "B", 22)
        pdf.cell(0, 12, "PAGAMENTO VIA PIX", align="C", new_x="LMARGIN", new_y="NEXT")

        pdf.ln(16)

        # QR code — centered, large
        qr_size = 55
        qr_x = x + (page_w - qr_size) / 2
        qr_y = pdf.get_y()

        buf = BytesIO(qrcode_png)
        pdf.image(buf, x=qr_x, y=qr_y, w=qr_size, h=qr_size)
        pdf.set_y(qr_y + qr_size + 6)

        # Instruction text
        pdf.set_font("Montserrat", "", 10)
        pdf.set_text_color(*MUTED_TEXT)
        pdf.cell(0, 6, "Escaneie o QR Code ou copie o c\u00f3digo abaixo", align="C",
                 new_x="LMARGIN", new_y="NEXT")

        pdf.ln(10)

        # Amount card
        card_h = 22
        card_y = pdf.get_y()
        pdf.set_fill_color(*TEAL_DARK)
        pdf.rect(x, card_y, page_w, card_h, "F")

        pdf.set_xy(x + 10, card_y + 3)
        pdf.set_font("MontserratSB", "", 8)
        pdf.set_text_color(180, 220, 220)
        pdf.cell(0, 5, "VALOR A PAGAR")
        pdf.set_xy(x + 10, card_y + 10)
        pdf.set_font("Montserrat", "B", 18)
        pdf.set_text_color(*WHITE)
        pdf.cell(0, 10, format_brl(total_amount))

        pdf.set_y(card_y + card_h + 12)

        # PIX key info card
        if pix_key:
            pdf.set_font("MontserratSB", "", 8)
            pdf.set_text_color(*MUTED_TEXT)
            pdf.cell(0, 5, "CHAVE PIX", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

            key_y = pdf.get_y()
            key_h = 14
            pdf.set_fill_color(*PURPLE_LIGHT)
            pdf.rect(x, key_y, page_w, key_h, "F")
            pdf.set_fill_color(*TEAL_DARK)
            pdf.rect(x, key_y, 3, key_h, "F")

            pdf.set_xy(x + 10, key_y + 3)
            pdf.set_font("Montserrat", "B", 11)
            pdf.set_text_color(*DARK_TEXT)
            pdf.cell(0, 8, pix_key)

            pdf.set_y(key_y + key_h + 10)

        # Pix Copia e Cola
        if pix_payload:
            pdf.set_font("MontserratSB", "", 8)
            pdf.set_text_color(*MUTED_TEXT)
            pdf.cell(0, 5, "PIX COPIA E COLA", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

            payload_y = pdf.get_y()
            pdf.set_fill_color(*ROW_ALT)
            pdf.set_draw_color(*BORDER_COLOR)

            pdf.set_xy(x + 6, payload_y + 4)
            pdf.set_font("Montserrat", "", 7)
            pdf.set_text_color(*DARK_TEXT)
            payload_cell_w = page_w - 12
            pdf.multi_cell(payload_cell_w, 4, pix_payload)

            payload_end_y = pdf.get_y() + 4
            payload_h = payload_end_y - payload_y
            # Draw background behind text (draw rect then rewrite text)
            pdf.set_fill_color(*ROW_ALT)
            pdf.rect(x, payload_y, page_w, payload_h, "F")
            pdf.set_draw_color(*BORDER_COLOR)
            pdf.set_line_width(0.3)
            pdf.rect(x, payload_y, page_w, payload_h, "D")

            pdf.set_xy(x + 6, payload_y + 4)
            pdf.set_font("Montserrat", "", 7)
            pdf.set_text_color(*DARK_TEXT)
            pdf.multi_cell(payload_cell_w, 4, pix_payload)

            pdf.set_y(payload_end_y + 4)

    def _draw_footer(self, pdf: FPDF, page_w: float) -> None:
        pdf.set_y(-30)
        pdf.set_draw_color(*BORDER_COLOR)
        pdf.set_line_width(0.3)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.l_margin + page_w, y)
        pdf.ln(5)
        pdf.set_font("Montserrat", "", 7)
        pdf.set_text_color(*MUTED_TEXT)
        pdf.cell(0, 5, "Documento gerado automaticamente", align="C")
